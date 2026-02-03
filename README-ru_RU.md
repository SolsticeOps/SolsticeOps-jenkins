<div align="center">
    <picture>
        <source
            srcset="https://github.com/SolsticeOps/SolsticeOps-core/docs/images/logo_dark.png"
            media="(prefers-color-scheme: light), (prefers-color-scheme: no-preference)"
        />
        <source
            srcset="https://github.com/SolsticeOps/SolsticeOps-core/docs/images/logo_light.png"
            media="(prefers-color-scheme: dark)"
        />
        <img src="https://github.com/SolsticeOps/SolsticeOps-core/docs/images/logo_light.png" />
    </picture>
</div>

# SolsticeOps-jenkins

Модуль управления Jenkins для SolsticeOps.

[English Version](README.md)

## Возможности
- Список задач и их статус
- Управление подключением
- Обновление учетных данных

## Установка
Добавьте как субмодуль в SolsticeOps-core:
```bash
git submodule add https://github.com/SolsticeOps/SolsticeOps-jenkins.git modules/jenkins
pip install -r modules/jenkins/requirements.txt
```

*Примечание: этот модуль зависит от библиотеки `docker` для логики установки.*
