package dev.hdast.pilot.auth;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import dev.hdast.pilot.api.ApiException;
import dev.hdast.pilot.config.PilotProperties;
import org.springframework.stereotype.Component;

/** Janela deslizante de 60 s por origem: toda tentativa de login conta, certa ou errada. */
@Component
public class LoginRateLimiter {

    private static final Duration WINDOW = Duration.ofSeconds(60);

    private final Map<String, Deque<Instant>> attempts = new ConcurrentHashMap<>();
    private final Clock clock;
    private final int max;

    public LoginRateLimiter(PilotProperties properties, Clock clock) {
        this.clock = clock;
        this.max = properties.loginMaxPerMinute();
    }

    public void register(String origin) {
        Instant now = clock.instant();
        Deque<Instant> window = attempts.computeIfAbsent(origin, k -> new ArrayDeque<>());
        synchronized (window) {
            while (!window.isEmpty() && window.peekFirst().isBefore(now.minus(WINDOW))) {
                window.pollFirst();
            }
            if (window.size() >= max) {
                long wait = Duration.between(now, window.peekFirst().plus(WINDOW)).toSeconds() + 1;
                throw ApiException.tooManyRequests(Math.max(wait, 1));
            }
            window.addLast(now);
        }
    }

    public void reset() {
        attempts.clear();
    }
}
