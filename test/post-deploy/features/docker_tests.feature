Feature: docker testing

  Scenario: ensure docker-compose containers are available and running
      Given docker-compose config "/usr/lucidum/docker-compose.yml" is present
       Then docker-compose images should be local
        And docker-compose containers should be running
