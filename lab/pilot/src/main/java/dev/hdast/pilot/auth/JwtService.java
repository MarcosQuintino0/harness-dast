package dev.hdast.pilot.auth;

import java.security.SecureRandom;
import java.time.Clock;
import java.time.Instant;
import java.util.Date;
import javax.crypto.SecretKey;

import dev.hdast.pilot.config.PilotProperties;
import io.jsonwebtoken.ExpiredJwtException;
import io.jsonwebtoken.JwtException;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import org.springframework.stereotype.Service;

/** Emite e valida o JWT (HS256). A chave é sorteada a cada subida: nada de segredo no repositório. */
@Service
public class JwtService {

    public enum Failure { INVALID, EXPIRED }

    public record Parsed(String username, Failure failure) {}

    private final SecretKey key;
    private final Clock clock;
    private final long ttlSeconds;

    public JwtService(PilotProperties properties, Clock clock) {
        byte[] secret = new byte[48];
        new SecureRandom().nextBytes(secret);
        this.key = Keys.hmacShaKeyFor(secret);
        this.clock = clock;
        this.ttlSeconds = properties.jwtTtlSeconds();
    }

    public long ttlSeconds() { return ttlSeconds; }

    public String issue(String username) {
        Instant now = clock.instant();
        return Jwts.builder().subject(username).issuedAt(Date.from(now))
                .expiration(Date.from(now.plusSeconds(ttlSeconds))).signWith(key).compact();
    }

    public Parsed parse(String token) {
        try {
            String sub = Jwts.parser().verifyWith(key).clock(() -> Date.from(clock.instant())).build()
                    .parseSignedClaims(token).getPayload().getSubject();
            return new Parsed(sub, null);
        } catch (ExpiredJwtException e) {
            return new Parsed(null, Failure.EXPIRED);
        } catch (JwtException | IllegalArgumentException e) {
            return new Parsed(null, Failure.INVALID);
        }
    }
}
