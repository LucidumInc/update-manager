Feature: user configuration testing

  Scenario: verify database and web user is correct
     Given we have a database and web user with user_id "1001"
      Then ensure database and web user exists

  Scenario: examine mongo database configuration
     Given we have a mongo installation at "/usr/lucidum/mongo"
       And mongo_data_dir exists at "/usr/lucidum/mongo/db"
      Then ensure mongo_data_dir is owned by user_id "1001"

  Scenario: examine mysql database configuration
     Given we have a mysql installation at "/usr/lucidum/mysql"
       And mysql_data_dir exists at "/usr/lucidum/mysql/db"
       And mysql_config exists at "/usr/lucidum/mysql/config/my_custom.cnf"
      Then ensure mysql_data_dir is owned by user_id "1001"
       And ensure mysql_config is owned by user_id "1001"

  Scenario: examine web configuration
     Given we have a web installation at "/usr/lucidum/web"
      Then ensure web_dir is owned by user_id "1001"
