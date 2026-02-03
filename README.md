# SolsticeOps-jenkins

Jenkins management module for SolsticeOps.

[Русская версия](README-ru_RU.md)

## Features
- Job list and status
- Connection management
- Credential updates

## Installation
Add as a submodule to SolsticeOps-core:
```bash
git submodule add https://github.com/SolsticeOps/SolsticeOps-jenkins.git modules/jenkins
pip install -r modules/jenkins/requirements.txt
```

*Note: This module depends on the `docker` python library for installation logic.*
