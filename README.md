# HNG STAGE 1 TASK
A project that takes 3 external APIs 
- [nationalize](https://nationalize.io/)
- [genderize](https://genderize.io/)
- [agify](https://agify.io/)
  
Uses the data from 3 APIs to create 4 endpoints
- POST `/api/profiles?name` to create a profile
- GET `api/profiles/{id}` to get a single profile with their id
- GET `api/profiles?gender&country_id&age_group` to get a profles based on whether the gender, age_group or country_id are provided
- DELETE `api/profiles/{id}` to delete a single profile based on their id

The data gotten from the POST request is stored in a POSTGRESQL database and subsequent methods fetch their data from it
