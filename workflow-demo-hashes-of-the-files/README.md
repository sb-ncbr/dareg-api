# Workflow demo
This folder contains a demo workflow that annotates whole directory structure with metadata, starting from the selected root file/folder in onedata. The metadata are hashes of the files for regular files and concatenation of child files hashes for directories. The folder consists of two other folders - code and schema. The code folder contains a working codebase and schema contains a json definition of workflow and lambdas.

## Code
This section describes how code works here. Here is the working code repository. Run docker build and docker push command in the code folder and use the published image(must be public) in onedata workflow lambda.

## Schema
Contains the valid json schema for workflow creation.

## How to use
Upload the json schema via onedata UI to create the workflow. The workflow schema references default image in dockerhub that provides the funcionality described above. If you want to publish and use your own image, create a new revision of a lambda that is used in the workflow and reference it to your docker repository image.