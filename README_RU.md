# Flandosync

Flandosync - небольшая утилита для синхронизации Minecraft-сборок.

Проект состоит из двух частей:

- `server/` генерирует манифесты сборок и раздаёт файлы по HTTP.
- `client/` - PyQt-лаунчер, который скачивает файлы из манифеста.

## Быстрый Старт

Полная документация по настройке и обслуживанию:

- English: [docs/INSTRUCTION.md](docs/INSTRUCTION.md)
- Русский: [docs/INSTRUCTION_RU.md](docs/INSTRUCTION_RU.md)

Дорожная карта:

- English: [docs/ROADMAP.md](docs/ROADMAP.md)
- Русский: [docs/ROADMAP_RU.md](docs/ROADMAP_RU.md)

План безопасности админпанели:

- English: [docs/ADMIN_SECURITY.md](docs/ADMIN_SECURITY.md)
- Русский: [docs/ADMIN_SECURITY_RU.md](docs/ADMIN_SECURITY_RU.md)

История изменений: [CHANGELOG.md](CHANGELOG.md)

### Сервер

```bash
cd server
cp config.example.json config.json
python server.py -generate example-pack
python server.py -serve
```

Файлы сборки нужно класть сюда:

```text
server/modpacks/<pack-name>/
```

Например:

```text
server/modpacks/example-pack/mods/example.jar
server/modpacks/example-pack/config/example.toml
```

После добавления, удаления или замены файлов нужно заново сгенерировать манифест:

```bash
python server.py -generate example-pack -version 1.2.1 -changelog "Обновлены моды"
```

Ключ доступа выводится в терминал и сохраняется в `key.txt`.
Клиент предупреждает игроков, когда версия сборки на сервере меняется.

### Клиент

```bash
cd client
cp flandosync_settings.example.json flandosync_settings.json
python client.py
```

В клиенте нужно ввести ключ доступа, выбрать корневую папку Minecraft-сборки и нажать синхронизацию.

Выбирать нужно корневую папку сборки, а не папку `mods`:

```text
C:\Users\<you>\AppData\Roaming\.minecraft
```

## Удаление Лишних Файлов

В клиенте есть опциональная галочка для удаления лишних файлов.

Если она включена, клиент удаляет файлы внутри синхронизируемых папок, например `mods/` или `config/`, которых нет в манифесте. Если выключена, локальные клиентские моды остаются на месте.

## Безопасность

Ключи Flandosync - это простые общие токены доступа. Не публикуй реальные `keys.json`, `key.txt`, приватные файлы сборок, IP-адреса, домены и личные конфиги.

Скачивание файлов по умолчанию использует временные download-token. Ключ игрока нужен, чтобы получить короткоживущий token, а сервер ограничивает параллельные скачивания для одного token.

В публичный GitHub-репозиторий нужно коммитить только example-конфиги.
