Feature: test lucidum crontabs

  Scenario: ensure necessary crontabs are installed
     Given crond is running
      When crontab directory "/usr/lucidum/crontabTask" exists and is not empty
       and crontab file "getSysInfo.sh" exists
       and crontab file "sysInfo_lib.py" exists
      Then ensure cronjobs are installed
