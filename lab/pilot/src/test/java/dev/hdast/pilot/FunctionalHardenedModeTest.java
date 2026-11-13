package dev.hdast.pilot;

import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = "pilot.vulnerable=false")
class FunctionalHardenedModeTest extends FunctionalBehaviour {
}
