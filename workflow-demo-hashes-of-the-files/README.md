# Workflow demo
This folder contains a demo workflow that annotates the whole directory structure with metadata, starting from the selected root file/folder in Onedata. The metadata are hashes of the files for regular files and concatenation of child file hashes for directories. The folder consists of two other folders—`code` and `schema`. The `code` folder contains a working codebase, and `schema` contains a JSON definition of the workflow and lambdas.

## Code
This section describes how the code works. Here is the working code repository. Run `docker build` and `docker push` commands in the `code` folder and use the published image (must be public) in the Onedata workflow lambda.

## Schema
Contains the valid JSON schema for workflow creation.

## How to use
Upload the JSON schema via the Onedata UI to create the workflow. The workflow schema references the default image in Docker Hub that provides the functionality described above. If you want to publish and use your own image, create a new revision of a lambda used in the workflow and reference it to your Docker repository image.
