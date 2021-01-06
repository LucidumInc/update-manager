Feature: airflow healthcheck testing

  Scenario: ensure airflow api is healthy
     Given we have "airflow-webserver" running
       and we have "airflow-scheduler" running
      When airflow healthcheck "http://172.17.0.1:9080/health" is available
      Then ensure healthcheck returns "200" http status code

  Scenario: ensure airflow dags are running
     Given we have "airflow-db-cleanup" dag configured
       and we have "airflow-log-cleanup" dag configured
       and we have "docker_dag" dag configured
      Then ensure dags are enabled
