Feature: lucidum directory testing

  Scenario: examine lucidum directory ownership
     Given we have a lucidum installation
      When lucidum directory is "/usr/lucidum"
      Then ensure files and directories do not have "root" ownership
