# Spike do Nuclei (branch spike/nuclei, nunca na main): alvo de pilha mínimo, Spring Boot com Actuator
# exposto de propósito. SÓ para o laboratório (rede interna, nada publicado no host).
#   docker build -t hdast-alvo-actuator:1.0.0 lab/actuator
# Imagens fixadas por digest, as mesmas da Clínica Piloto (lab/pilot/Dockerfile).
FROM maven:3.9.11-eclipse-temurin-21@sha256:6fdc855a6ed81d288ca7ca37ac6ff5e9308b612485c0801d70b25a858c83d237 AS build
WORKDIR /build
COPY pom.xml ./
RUN mvn -B -ntp -q dependency:resolve dependency:resolve-plugins
COPY src ./src
RUN mvn -B -ntp -q package -DskipTests

FROM eclipse-temurin:21-jre-alpine@sha256:ac05c3c42b7c2f1a52c9bd52f01041fa1958231b15ebeae7420429cbc5baf474
RUN addgroup -S -g 10001 app && adduser -S -D -u 10001 -G app app
WORKDIR /app
COPY --from=build /build/target/alvo-actuator.jar /app/app.jar
USER 10001:10001
ENV JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=70 -XX:+ExitOnOutOfMemoryError -Djava.io.tmpdir=/tmp"
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
