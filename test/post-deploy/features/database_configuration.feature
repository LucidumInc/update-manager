Feature: database configuration testing

  Scenario: verify database user is correct
     Given we have a database user with user_id "1001"
      Then ensure database user exists

  Scenario: examine mongo database configuration
     Given we have a mongo installation at "/usr/lucidum/mongo"
       And mongo_data_dir exists at "/usr/lucidum/mongo/db"
      Then ensure mongo_data_dir is owned by database user

  Scenario: examine mysql database configuration
     Given we have a mysql installation at "/usr/lucidum/mysql"
       And mysql_data_dir exists at "/usr/lucidum/mysql/db"
       And mysql_config exists at "/usr/lucidum/mysql/config/my_custom.cnf"
      Then ensure mysql_data_dir is owned by database user
       And ensure mysql_config is owned by database user
