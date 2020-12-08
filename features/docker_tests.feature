Feature: docker testing

  Scenario: ensure docker images and containers are available and running
      Given docker image "mvp1_backend:latest" is local
        and docker image "python/ml:latest" is local
        and docker image "bitnami/mysql:8.0.20" is local
        and docker image "bitnami/mongodb:4.0.14-r29" is local
        and docker image "graphiteapp/graphite-statsd:1.1.7-3" is local
       Then docker containers should be running
