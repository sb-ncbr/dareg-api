# Create your first job in DAREG
This text is explaining how to run your first job in DAREG application utilizing workflow-demo-hashes-of-the-files workflow present in the repository. All the parameters on this page are corresponding to workflow-demo-hashes-of-the-files workflow, so feel free to use them.

Prerequisities: Properly configured facility, project and dataset(we will run a job on dataset). Create demo workflow in onedata via json from the code reposiotry.

## Configure your first workflow
Prepare: Take a workflow id from the onedata you want to create workflow record in DAREG.

1. Configure workflow id from one data.
2. Configure name, description
3. Set revision based on the workflow revision in onedata
4. Configure input json. For the demo workflow it is like:
``` 
{
  "appConfig": {
    "storeId": "cd644c29d451ad3eff2a03b828549b26b80162",
    "algorithm": "md5",
    "metadataKey": "checksum"
  },
  "appConfigDetails": {
    "algorithm": {
      "type": "string",
      "description": "Description of the algorithm param"
    },
    "metadataKey": {
      "type": "string",
      "description": "Description of the metadataKey param"
    }
  },
  "onedataInputStore": "8ef862da9c661ccded6762af6d51449e50fc90",
  "onedataOutputStore": "b3416eff41b9d7d0b2751d7f439a5995bfaa64"
} 
```
Values for onedataInputStore and onedataOutputStore can be found inside workflow detail in onedata - stores are the boxes in the bottom of the screen after the header 'Stores:', see picture
![Workflow Configuration](./docs/images/workflow_admin_ui.png)
Configure store ID also for appConfig store.
Now let's configure the input parameters. Inside nested 'appConfig' json, put there all the parameters your container is expecting with a default value as a field value(remember there is also storeId corresponding to the store where the app config is expected to be uploaded). For all the input parameters, create an 'appConfigDetails' nested json describing for all the parameters what type they have along with a description what the parameter stands for. To better understand what is where see example json above. Now the job would expect to have configured all the parameters configured in workflow.
5. Select workflow type.

## Create your first job
![Job configuration](./docs/images/job_admin_ui.png)
1. Select a workflow you would like to use as a template for run job
2. Select input object type - project, dataset or experimen - in our case it's dataset
3. Provide the id of the input object. In our case the id of the prepared DAREG dataset.
4. Select output object type - dataset or experiment - in our case it's experiment. This is the output where the results of the job will be stored.
5. Provide the id of the output object.
6. Insert name and description of the job.
7. Insert your appConfig json with all the parameters specified in workflow. In our case:
```
{
    "algorithm": "sha256",
    "metadataKey": "hash_of_the_file"
}
```
8. Submit

Now the job is submitted. For this particular job it takes about two minutes to finish.