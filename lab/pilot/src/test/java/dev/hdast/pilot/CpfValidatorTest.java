package dev.hdast.pilot;

import static org.assertj.core.api.Assertions.assertThat;

import dev.hdast.pilot.validation.CpfValidator;
import org.junit.jupiter.api.Test;

class CpfValidatorTest {

    @Test
    void aceita_cpfSinteticoComDigitosValidos() {
        assertThat(CpfValidator.hasValidCheckDigits("52998224725")).isTrue();
        assertThat(CpfValidator.hasValidCheckDigits("11144477735")).isTrue();
    }

    @Test
    void recusa_digitoErradoESequenciaRepetida() {
        assertThat(CpfValidator.hasValidCheckDigits("52998224726")).isFalse();
        assertThat(CpfValidator.hasValidCheckDigits("11111111111")).isFalse();
    }
}
