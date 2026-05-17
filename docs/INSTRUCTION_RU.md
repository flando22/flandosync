# Инструкция Flandosync

Этот документ объясняет, как опубликовать, настроить, запустить и обслуживать Flandosync.

Flandosync состоит из двух независимых частей:

- Сервер: хранит файлы сборок, генерирует манифесты, хранит ключи доступа и раздаёт файлы по HTTP.
- Клиент: настольное приложение для игроков. Игрок вводит ключ доступа, выбирает папку Minecraft-сборки и синхронизирует файлы с сервера.

## Структура Репозитория

```text
flandosync-public/
  client/
    client.py
    flandosync_settings.example.json
    requirements.txt
    README.md
  server/
    server.py
    config.example.json
    requirements.txt
    README.md
  docs/
    INSTRUCTION.md
    INSTRUCTION_RU.md
  .gitignore
  README.md
```

Рабочие файлы специально исключены из Git:

```text
server/config.json
server/keys.json
server/modpacks/
client/flandosync_settings.json
client/flandosync_client.json
```

Не публикуй реальные ключи, приватные файлы модпака, IP-адреса, домены или локальные пути игроков.

## Настройка Сервера

Установи Python 3.10 или новее.

Скопируй пример конфига:

```bash
cd server
cp config.example.json config.json
```

Отредактируй `config.json`:

```json
{
    "server_url": "http://localhost:8000",
    "modpacks_dir": "./modpacks",
    "port": 8000
}
```

Поля:

- `server_url`: запасной адрес сервера, если в HTTP-запросе нет заголовка `Host`.
- `modpacks_dir`: папка, где лежат сборки.
- `port`: HTTP-порт сервера.

Сервер поддерживает и локальный доступ, и публичный доступ. Если клиент приходит по локальному IP, сервер отдаёт локальные ссылки. Если клиент приходит через домен, сервер отдаёт ссылки с доменом. Это делается через HTTP-заголовок `Host`.

## Создание Сборки

Создай папку сборки:

```bash
mkdir -p modpacks/example-pack/mods
mkdir -p modpacks/example-pack/config
```

Положи файлы внутрь папки сборки:

```text
modpacks/example-pack/mods/some-mod.jar
modpacks/example-pack/config/some-config.toml
```

Сгенерируй манифест:

```bash
python server.py -generate example-pack
```

Можно сразу указать версию и changelog:

```bash
python server.py -generate example-pack -version 1.2.0 -changelog "Добавлены новые моды"
```

Для длинного changelog можно использовать UTF-8 файл:

```bash
python server.py -generate example-pack -version 1.2.0 -changelog-file changelog.txt
```

Команда создаёт или обновляет:

```text
modpacks/example-pack/manifest.json
modpacks/example-pack/key.txt
keys.json
```

Ключ доступа будет выведен в терминал. Его нужно дать игрокам.

## Обновление Сборки

Когда ты добавляешь, удаляешь или заменяешь файлы, заново сгенерируй манифест:

```bash
cd server
python server.py -generate example-pack -version 1.2.1 -changelog "Обновлены моды"
```

Игрокам не нужен новый клиент. Им достаточно снова нажать `SYNC`.
Клиент предупредит игроков, если версия на сервере отличается от последней синхронизированной версии, и покажет changelog, если он есть.

Сгенерированный ключ остаётся стабильным. Он переиспользуется из `key.txt` или `keys.json`.

## Запуск Сервера

Запусти:

```bash
cd server
python server.py -serve
```

Полезные URL:

```text
http://localhost:8000/project_by_key?key=<ACCESS_KEY>
http://localhost:8000/modpacks/example-pack/manifest.json
```

Для настоящего сервера лучше запускать Flandosync через менеджер процессов: systemd, tmux, screen, Docker или другой удобный способ.

## Настройка Клиента

Установи зависимости:

```bash
cd client
python -m pip install -r requirements.txt
```

Скопируй пример настроек:

```bash
cp flandosync_settings.example.json flandosync_settings.json
```

Отредактируй `flandosync_settings.json`:

```json
{
    "server_url": "http://your-server.example:8000",
    "app_name": "Flandosync Client",
    "theme": "dark"
}
```

Запусти:

```bash
python client.py
```

## Настройки Клиента

Нажми `Settings` в клиенте, чтобы изменить:

- адрес сервера;
- тему.
- время кэша манифеста;
- количество потоков скачивания;
- таймаут запросов.

В окне настроек есть кнопка `Test server`. Она проверяет, доступен ли настроенный Flandosync-сервер.

Настройки хранятся в:

```text
flandosync_settings.json
```

`manifest_cache_ttl_seconds` задаёт, сколько секунд клиент может использовать недавно скачанный манифест. Значение `0` отключает кэш манифеста.

`download_workers` задаёт количество параллельных скачиваний. Для небольшого приватного сервера лучше держать значение низким: `2-4`.

`request_timeout_seconds` задаёт таймаут HTTP-запросов.

## Использование Клиента

1. Введи ключ доступа.
2. Нажми `Add modpack`.
3. Выбери корневую папку Minecraft-сборки.
4. Выбери сборку в списке.
5. Нажми `SYNC`.

Выбирать нужно корневую папку сборки, а не папку `mods`.

Правильно:

```text
C:\Users\<name>\AppData\Roaming\.minecraft
```

Неправильно:

```text
C:\Users\<name>\AppData\Roaming\.minecraft\mods
```

В манифесте пути выглядят как `mods/example.jar`, поэтому если выбрать сразу `mods`, получится `mods/mods/example.jar`.

## Управление Сохранёнными Сборками

Кликни правой кнопкой по сборке в списке, чтобы открыть контекстное меню.

Доступные действия:

- `Rename`: задаёт локальное отображаемое имя.
- `Remove`: удаляет сборку из локального списка.

Переименование не меняет имя сборки на сервере. Если серверное имя `aerocraft`, а локальное имя `Моя сборка`, клиент покажет:

```text
Моя сборка (aerocraft)
```

Удаление сборки по умолчанию оставляет локальные файлы на месте. В окне подтверждения есть дополнительная галочка:

```text
Also permanently delete synced files
```

Если включить эту галочку, клиент скачает свежий манифест и удалит только файлы, перечисленные в манифесте. Вся выбранная папка Minecraft не удаляется.

## Галочка Delete Extra Files

В клиенте есть галочка `Delete extra files`.

Если она выключена:

- файлы из манифеста скачиваются или обновляются;
- локальные клиентские моды, которых нет в манифесте, остаются на месте.

Если она включена:

- файлы из манифеста скачиваются или обновляются;
- файлы внутри синхронизируемых папок, например `mods/` и `config/`, удаляются, если их нет в манифесте.

Включай эту опцию только когда нужна чистая папка клиента, строго совпадающая со сборкой на сервере.

## Логи И Список Изменений

Клиент отдельно показывает список изменений синхронизации:

- скачанные файлы;
- пропущенные файлы;
- удалённые файлы.

Кнопка `Export logs` сохраняет консольный лог и список изменений в текстовый файл.

## Сборка Windows EXE

Установи зависимости для сборки:

```powershell
cd client
python -m pip install -r requirements.txt pyinstaller
```

Собери приложение:

```powershell
python -m PyInstaller --noconfirm --clean --onefile --windowed --name FlandosyncLauncher client.py
```

Результат будет здесь:

```text
client/dist/FlandosyncLauncher.exe
```

EXE нужно отдавать вместе с:

```text
flandosync_settings.json
```

Не отдавай `flandosync_client.json`, если не хочешь передать сохранённые локальные проекты.

## Рекомендуемый Пакет Для Игроков

Для игроков обычно достаточно:

```text
FlandosyncLauncher.exe
flandosync_settings.json
README.txt
```

В README для игроков стоит указать:

- ключ доступа;
- адрес сервера, если нужно;
- напоминание выбирать корневую папку Minecraft-сборки;
- предупреждение про `Delete extra files`.

## Проверка Перед Публикацией

Перед загрузкой на GitHub убедись, что в репозиторий не попали:

```text
keys.json
key.txt
manifest.json
modpacks/
flandosync_client.json
real config.json
real flandosync_settings.json
IP addresses
private domains
usernames
local filesystem paths
```

Коммитить нужно только:

```text
config.example.json
flandosync_settings.example.json
source files
requirements
docs
```

## Частые Команды

Сгенерировать или обновить сборку:

```bash
python server.py -generate example-pack
```

Запустить сервер:

```bash
python server.py -serve
```

Проверить ключ:

```bash
curl "http://localhost:8000/project_by_key?key=<ACCESS_KEY>"
```

Проверить манифест:

```bash
curl "http://localhost:8000/modpacks/example-pack/manifest.json"
```

## Решение Проблем

Если клиент пишет, что сервер недоступен:

- проверь, что `python server.py -serve` запущен;
- проверь, что порт из `config.json` открыт;
- проверь, что `flandosync_settings.json` указывает на правильный сервер;
- открой `/project_by_key?key=<ACCESS_KEY>` в браузере.

Если клиент ничего не скачивает:

- заново сгенерируй манифест;
- открой `manifest.json` и проверь, что `files` не пустой;
- убедись, что файлы лежали внутри папки сборки до запуска `-generate`.
- если включён кэш манифеста, подожди время кэша или поставь `manifest_cache_ttl_seconds` в `0`.

Если файлы появились в `mods/mods`:

- пользователь выбрал папку `mods` вместо корня Minecraft-сборки;
- удали неправильно созданную папку и добавь сборку заново, выбрав правильный корень.

Если удаляются клиентские моды:

- выключи `Delete extra files`;
- включай эту галочку только для строгой очистки.
