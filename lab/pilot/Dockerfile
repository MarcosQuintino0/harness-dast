# syntax=docker/dockerfile:1.7
# Clinica Piloto: alvo de treino local do harness-dast. Software INTENCIONALMENTE VULNERAVEL
# (modo padrao). Nunca rode fora de localhost/Docker local.
#
# Build de ponta a ponta, sem JDK no host:
#   docker build -t hdast-clinica-piloto:1.0.0 lab/pilot
# Os testes de integracao rodam no build (falham o build). Para pular:
#   docker build --build-arg SKIP_TESTS=true ...
#
# Imagens fixadas por tag E digest do indice multi-arquitetura (lido no pull, 2026-11-13):
#   maven:3.9.11-eclipse-temurin-21        https://hub.docker.com/_/maven
#   eclipse-temurin:21-jre-alpine (21.0.13) https://hub.docker.com/_/eclipse-temurin

FROM maven:3.9.11-eclipse-temurin-21@sha256:6fdc855a6ed81d288ca7ca37ac6ff5e9308b612485c0801d70b25a858c83d237 AS build
WORKDIR /build
COPY pom.xml ./
RUN --mount=type=cache,target=/root/.m2 mvn -B -ntp -q dependency:resolve dependency:resolve-plugins
COPY src ./src
# Arquivos lidos pelos testes (deriva do OpenAPI, SQL de limpeza, documentos de exemplo).
COPY documentos ./documentos
COPY cleanup ./cleanup
COPY openapi.json ./openapi.json
ARG SKIP_TESTS=false
# Mude o valor para forcar a reexecucao dos testes sem invalidar o cache das dependencias.
ARG TESTS_RERUN=0
RUN --mount=type=cache,target=/root/.m2 mvn -B -ntp package -DskipTests=${SKIP_TESTS}

# Regenera o openapi.json a partir da aplicacao (nao faz parte da imagem final):
#   docker build --target openapi-out --output type=local,dest=lab/pilot lab/pilot
FROM build AS openapi-export
RUN --mount=type=cache,target=/root/.m2 mkdir /out  && PILOT_OPENAPI_OUT=/out/openapi.json mvn -B -ntp test -Dtest=OpenApiDriftTest
FROM scratch AS openapi-out
COPY --from=openapi-export /out/openapi.json /openapi.json

FROM eclipse-temurin:21-jre-alpine@sha256:ac05c3c42b7c2f1a52c9bd52f01041fa1958231b15ebeae7420429cbc5baf474 AS runtime
RUN addgroup -S -g 10001 pilot && adduser -S -D -u 10001 -G pilot pilot
WORKDIR /app
COPY --from=build /build/target/clinica-piloto.jar /app/app.jar
COPY documentos /app/documentos
RUN printf 'clinica-piloto build-info\nversion=1.0.0\nmarker=PILOT-BUILD-INFO-7c1e4b\n' > /app/build-info.txt \
 && chmod -R a+rX /app
USER 10001:10001
ENV JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=70 -XX:+ExitOnOutOfMemoryError -Djava.io.tmpdir=/tmp"
EXPOSE 8080 9091
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
