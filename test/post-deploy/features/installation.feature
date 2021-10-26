Feature: lucidum installation directory testing

  Scenario: examine lucidum directory ownership
     Given we have a lucidum installation
      When lucidum directory is "/usr/lucidum"
      Then ensure files and directories do not have "root" ownership

  Scenario: examine lucidum directory permissions
     Given we have a lucidum installation
      When lucidum directory is "/usr/lucidum"
      Then ensure files and directories do not have world writable "2" "3" "6" "7" bits
