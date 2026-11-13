package dev.hdast.pilot.validation;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;

/** CPF com dígitos verificadores válidos (só confere o dígito; o formato é do @Pattern). */
@Documented
@Constraint(validatedBy = CpfValidator.class)
@Target({ElementType.FIELD, ElementType.RECORD_COMPONENT, ElementType.PARAMETER})
@Retention(RetentionPolicy.RUNTIME)
public @interface Cpf {
    String message() default "dígitos verificadores do CPF inválidos";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
