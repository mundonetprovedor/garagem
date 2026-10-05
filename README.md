# Garage Logbook

O Garage Logbook registra o histórico de manutenção do seu veículo a partir de uma interface web auto-hospedada, simples e elegante. Tem suporte a upload de imagens e documentos (pense em fotos de reparos ou PDFs de recibos), autenticação com níveis de acesso, importação e exportação CSV para registros de manutenção existentes, e uma interface escura e performática rodando em um container Docker para fácil implantação.

Desenvolvido e mantido por [Hyprlab](https://hyprlab.co)

---

## Recursos

- **Suporte a vários usuários**: Cada usuário tem sua própria garagem com veículos e registros de manutenção isolados
- **Gerenciamento de veículos**: Adicione, edite e exclua veículos com ano, marca, modelo, VIN, data de compra e foto
- **Registros de manutenção**: Registre reparos, manutenções, upgrades e vistorias com data, quilometragem, fornecedor, custo, anotações e galerias de fotos
- **Recibos em PDF**: Envie documentos PDF (recibos, faturas, orçamentos) para qualquer registro de manutenção
- **Lembretes de serviço**: Defina um intervalo por veículo e veja o que está vencido, vencendo em breve ou em atraso. Um alternador escolhe o que cada contador conta: quilometragem ("fluido da transmissão a cada 30.000 km") ou tempo ("fluido de freio a cada 24 meses"). Os lembretes se ancoram aos seus registros de serviço, então registrar o serviço avança automaticamente o próximo vencimento, e ao adicionar um registro você pode marcar quais contadores reiniciar a partir da quilometragem ou da data
- **Painel**: Estatísticas rápidas de total de veículos, registros de serviço, dinheiro gasto e serviços pendentes, com intervalos configuráveis e uma lista de serviços próximos em todos os veículos
- **Busca e ordenação**: Busca ao vivo em veículos e registros de manutenção com várias opções de ordenação
- **Importação e exportação CSV**: Importe registros de manutenção a partir de arquivos CSV com mapeamento de campos e pré-visualização de dry-run, ou exporte todos os registros de qualquer veículo
- **Duplicar registros**: Duplique rapidamente um registro de manutenção existente como ponto de partida
- **Acesso por níveis**: Dois papéis de usuário com permissões aplicadas:
  - **Admin**: Acesso total aos dados de todos os usuários, gerenciamento de usuários e todos os recursos
  - **Editor**: Permissões configuráveis por usuário (veja abaixo)
- **Permissões granulares**: Admins podem alternar capacidades individuais para cada editor:
  - Adicionar / Editar / Excluir veículos
  - Adicionar / Editar / Excluir registros de manutenção
  - Importar CSV / Exportar CSV
- **Segurança no primeiro acesso**: A conta admin padrão é forçada a trocar a senha no primeiro login
- **Galeria de imagens**: Envie várias fotos por registro de manutenção com visualizador lightbox
- **Tema claro e escuro**: Alterne entre modo claro e escuro em Configurações, salvo por usuário
- **Configurações por usuário**: Cada usuário pode personalizar suas preferências de painel e tema
- **Responsivo para celular**: Funciona em desktop, tablet e celular
- **Pronto para Docker**: Distribuído como imagem Docker com armazenamento em volume persistente

---

## Requisitos

- Docker e Docker Compose

Só isso. Todo o resto é resolvido pelo container.

---

## Início rápido

### 1. Crie um diretório de projeto

```bash
mkdir ~/garage-logbook && cd ~/garage-logbook
```

### 2. Baixe o arquivo compose e o modelo de ambiente

```bash
curl -O https://raw.githubusercontent.com/hyprlab/garage-logbook/main/docker-compose.yml
curl -O https://raw.githubusercontent.com/hyprlab/garage-logbook/main/.env.example
```

Ou crie os arquivos manualmente:

<details>
<summary><strong>docker-compose.yml</strong></summary>

```yaml
services:
  garage-logbook:
    image: hyprlab/garage-logbook:latest
    container_name: garage-logbook
    restart: unless-stopped
    ports:
      - "${APP_PORT:-5000}:5000"
    volumes:
      - garage-data:/data
    env_file:
      - .env
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:5000/login')"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s

volumes:
  garage-data:
    driver: local
```

</details>

<details>
<summary><strong>.env.example</strong></summary>

```bash
# Configuração de ambiente do Garage Logbook
# Copie este arquivo para .env e atualize os valores abaixo.
#
#   cp .env.example .env
#

# ─── OBRIGATÓRIO ──────────────────────────────────────────
# Chave de criptografia da sessão. Gere uma com:
#   python3 -c "import secrets; print(secrets.token_hex(32))"
# ou:
#   openssl rand -hex 32
SECRET_KEY=CHANGE-ME-replace-with-a-random-string

# ─── OPCIONAL ──────────────────────────────────────────
# Porta em que o app fica acessível (padrão: 5000)
APP_PORT=5000

# Caminho do banco de dados dentro do container (normalmente não precisa mudar)
DATABASE_PATH=/data/garage_logbook.db

# Pasta de uploads dentro do container (normalmente não precisa mudar)
UPLOAD_FOLDER=/data/uploads
```

</details>

### 3. Crie seu arquivo de ambiente

```bash
cp .env.example .env
```

### 4. Gere uma secret key e atualize o arquivo .env

Gere uma chave:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Abra `.env` no seu editor e substitua o placeholder de `SECRET_KEY` pelo valor gerado:

```
SECRET_KEY=your-generated-key-here
```

Você também pode mudar a porta aqui se `5000` já estiver em uso:

```
APP_PORT=8080
```

### 5. Inicie a aplicação

```bash
docker compose up -d
```

### 6. Faça login

Abra seu navegador em `http://localhost:5000` (ou a porta que você configurou).

| | |
|---|---|
| **Usuário** | `admin` |
| **Senha** | `admin` |

Você será solicitado a definir uma nova senha no primeiro login.

---

## Atualização

Quando uma nova versão for lançada:

```bash
docker compose pull
docker compose up -d
```

Seus dados ficam em um volume Docker e não são afetados pelas atualizações. Seu arquivo `.env` permanece intacto.

---

## Configuração

Toda a configuração é gerenciada pelo arquivo `.env`. O arquivo `.env.example` documenta todas as opções disponíveis.

| Variável | Obrigatória | Descrição | Padrão |
|---|---|---|---|
| `SECRET_KEY` | **Sim** | Chave de criptografia de sessão do Flask | Nenhuma |
| `APP_PORT` | Não | Porta em que o app fica acessível | `5000` |
| `DATABASE_PATH` | Não | Caminho do banco de dados dentro do container | `/data/garage_logbook.db` |
| `UPLOAD_FOLDER` | Não | Caminho de uploads dentro do container | `/data/uploads` |

> **Nota:** O arquivo `.env` contém sua chave secreta e não deve ser commitado no controle de versão nem compartilhado publicamente.

### Rodando atrás de um reverse proxy

Se estiver rodando atrás do Nginx, Caddy, Nginx Proxy Manager ou similar, aponte o proxy para a porta definida em `APP_PORT` (padrão `5000`). Nenhuma configuração adicional é necessária no app.

---

## Suporte a vários usuários

Cada usuário tem sua própria garagem isolada. Veículos e registros de manutenção criados por um usuário não são visíveis para outros usuários.

**Usuários admin** podem ver todos os veículos e registros de todos os usuários, com rótulos de dono em cada cartão de veículo. Isso facilita o gerenciamento de uma instância compartilhada onde vários membros da família ou da equipe acompanham seus próprios veículos.

Para criar usuários adicionais, vá em **Settings → Users → Add User** (somente admin).

---

## Papéis de usuário e permissões

O Garage Logbook usa dois papéis. O papel de viewer foi removido em favor de alternadores de permissões granulares no papel de editor.

### Admin

Acesso completo e irrestrito a tudo: todos os veículos e registros de todos os usuários, gerenciamento de usuários, importação, exportação e todas as operações CRUD.

### Editor

O acesso é limitado aos veículos e registros do próprio usuário. Admins podem configurar exatamente o que cada editor pode fazer ativando permissões individuais:

| Permissão | Padrão | Descrição |
|---|---|---|
| Adicionar veículos | ✓ | Criar novos veículos |
| Editar veículos | ✓ | Modificar veículos existentes |
| Excluir veículos | ✓ | Remover veículos e todos os registros associados |
| Adicionar registros | ✓ | Criar registros de manutenção |
| Editar registros | ✓ | Modificar registros existentes |
| Excluir registros | ✓ | Remover registros de manutenção |
| Importar CSV | Desligado | Importar registros de arquivos CSV |
| Exportar CSV | ✓ | Exportar registros para arquivos CSV |

As permissões são configuradas por usuário em **Settings → Users → Edit**.

---

## Backup e restauração

### Backup

```bash
docker compose stop
docker run --rm \
  -v garage-logbook_garage-data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/garage-logbook-backup.tar.gz -C /data .
docker compose up -d
```

Isso cria `garage-logbook-backup.tar.gz` no seu diretório atual contendo o banco de dados e todas as imagens e documentos enviados.

### Restauração

```bash
docker compose stop
docker run --rm \
  -v garage-logbook_garage-data:/data \
  -v $(pwd):/backup \
  alpine sh -c "rm -rf /data/* && tar xzf /backup/garage-logbook-backup.tar.gz -C /data"
docker compose up -d
```

---

## Compilando a partir do código-fonte

Se preferir compilar a imagem Docker você mesmo em vez de baixá-la do Docker Hub:

```bash
git clone https://github.com/hyprlab/garage-logbook.git
cd garage-logbook
cp .env.example .env
# Edite o .env e defina sua SECRET_KEY
```

Crie um `docker-compose.override.yml` junto a ele. O Compose mescla esse arquivo automaticamente, então você obtém um build local sem editar o `docker-compose.yml` versionado:

```yaml
services:
  garage-logbook:
    build: .
    image: garage-logbook-dev:latest
```

A tag `image:` separada evita que seu build local sobrescreva o `hyprlab/garage-logbook:latest` publicado no cache de imagens. Esse arquivo é gitignored, então sua configuração local nunca acaba em um commit.

```bash
docker compose up -d --build
```

### Rodando sem Docker

O Garage Logbook também pode rodar diretamente em um sistema Linux com Python 3.10+:

```bash
git clone https://github.com/hyprlab/garage-logbook.git
cd garage-logbook
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

export SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
python app.py
```

O app ficará disponível em `http://localhost:5000`. O banco de dados e os uploads serão armazenados no diretório do projeto.

---

## Estrutura do projeto

```
garage-logbook/
├── app.py                    # Aplicação Flask
├── requirements.txt          # Dependências Python
├── Dockerfile                # Instruções de build do container
├── docker-compose.yml        # Configuração do Compose (baixa a imagem publicada)
├── .env.example              # Modelo de variáveis de ambiente
├── CONTRIBUTING.md           # Convenções de commit, versionamento e release
├── .github/
│   └── workflows/
│       └── release.yml       # Cria releases no GitHub automaticamente ao enviar uma tag
├── tools/                    # Scripts de release e git hooks (veja CONTRIBUTING.md)
├── static/
│   ├── css/style.css         # Folha de estilos (temas escuro + claro)
│   ├── js/app.js             # JavaScript do frontend
│   ├── garage-logbook_logo.svg
│   ├── hyprlab_logo.png
│   └── favicon.png
└── templates/
    ├── index.html            # Template principal da aplicação
    └── login.html            # Página de login
```

---

## Aviso sobre IA

O Garage Logbook é desenvolvido por um mantenedor humano trabalhando com IA generativa como ferramenta de desenvolvimento:

- **Código**: a grande maioria do Python, JavaScript e CSS deste repositório foi escrita com o Claude da Anthropic (via Claude Code), seguindo as diretrizes do mantenedor. O mantenedor decide o que será construído, revisa os resultados, testa cada release e aprova tudo que é publicado.
- **Texto**: documentação, notas de release e textos do app são em grande parte redigidos por IA e editados por humanos.
- **O app em si não contém IA.** O Garage Logbook não tem recursos de IA e não faz chamadas a serviços de IA. Seus registros de veículos ficam no seu próprio banco de dados. IA foi usada para *construir* o app, não para executá-lo.

Relatos de bugs e pull requests são bem-vindos de humanos e suas ferramentas de IA; tudo que é mesclado recebe a mesma revisão humana. Veja [CONTRIBUTING.md](CONTRIBUTING.md) para as convenções.

## Licença

O Garage Logbook é software livre, licenciado sob a **GNU Affero General Public License v3.0 (AGPL-3.0)**. Você tem liberdade para usar, estudar, compartilhar e modificar sob os termos dessa licença. Como a AGPL cobre uso em rede, se você executar uma versão modificada do Garage Logbook como um serviço acessível pela rede, também deve disponibilizar o código-fonte correspondente aos seus usuários.

Veja o arquivo [LICENSE](LICENSE) para o texto completo.

---

## Sobre

O Garage Logbook é desenvolvido por [Hyprlab](https://hyprlab.co)

Versão atual: **0.3.2**
