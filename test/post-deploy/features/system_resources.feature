Feature: system resources minimum requirements testing

  Scenario: examine running system for minimum memory requirements
     Given we have a running lucidum system
      When lucidum minimum memory is "64000000000" bytes
      Then ensure system memory is sufficient

  Scenario: examine running system for minimum cpu requirements
     Given we have a running lucidum system
      When lucidum minimum cpu is "8" cores
      Then ensure system cpu is sufficient

  Scenario: examine running system for minimum disk requirements
     Given we have a running lucidum system
      When lucidum minimum disk is "1000000000000" bytes
      Then ensure system disk is sufficient
