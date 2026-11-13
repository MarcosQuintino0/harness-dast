package dev.hdast.pilot.validation;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public class CpfValidator implements ConstraintValidator<Cpf, String> {

    @Override
    public boolean isValid(String value, ConstraintValidatorContext context) {
        // Nulo e formato errado ficam por conta de @NotBlank/@Pattern: um erro por regra.
        return value == null || !value.matches("[0-9]{11}") || hasValidCheckDigits(value);
    }

    /** Algoritmo módulo 11 da Receita Federal. Rejeita sequências de dígitos iguais. */
    public static boolean hasValidCheckDigits(String cpf) {
        if (cpf.chars().distinct().count() == 1) {
            return false;
        }
        return digit(cpf, 9) == cpf.charAt(9) - '0' && digit(cpf, 10) == cpf.charAt(10) - '0';
    }

    private static int digit(String cpf, int length) {
        int sum = 0;
        for (int i = 0; i < length; i++) {
            sum += (cpf.charAt(i) - '0') * (length + 1 - i);
        }
        int rest = (sum * 10) % 11;
        return rest == 10 ? 0 : rest;
    }
}
