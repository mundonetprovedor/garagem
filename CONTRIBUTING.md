# Contribuindo

As convenções seguidas por quem edita este repositório, humano ou IA. Relatos
de bugs, ideias e pull requests são todos bem-vindos, e um relato de bug claro
muitas vezes é tão útil quanto um patch.

## Configurando o ambiente

```sh
git config core.hooksPath tools/git-hooks     # uma vez por clone ou worktree
docker compose up -d --build                  # http://localhost:5000
```

Os hooks aplicam as regras de commit abaixo. Sem `core.hooksPath`, eles
silenciosamente não fazem nada, então configure em todo clone e todo worktree.

## Commits

**O histórico pertence ao mantenedor.** Commits não carregam atribuição a
ferramentas de IA: nenhuma linha `Co-Authored-By:` para o Claude ou qualquer
outro assistente, nenhum rodapé "Generated with", nenhuma linha de sessão, em
um commit, mensagem de tag, corpo de pull request ou corpo de release. O
[Aviso sobre IA](README.md#aviso-sobre-ia) declara como o projeto é construído, uma
única vez, para todo o repositório. Um único trailer fora do lugar coloca a
ferramenta no painel de Contribuidores do GitHub, e removê-lo depois significa
reescrever o histórico.

Um trailer `Co-Authored-By:` ainda é como uma **pessoa** é creditada, com o
endereço noreply do GitHub que resolve para o perfil dela (veja [Créditos](#cr�ditos)).

Os assuntos seguem [Conventional Commits](https://www.conventionalcommits.org):
`type(area): summary`, minúsculas depois dos dois-pontos, imperativo, sem
ponto final, no máximo 72 caracteres e idealmente mais perto de 50.

- Tipos: `feat`, `fix`, `perf`, `refactor`, `docs`, `build`, `ci`, `test`,
  `style`, `chore`, `revert`. Um `!` após o tipo (`feat(db)!:`) marca uma
  mudança incompatível. O tipo não é decoração: `tools/next-version.sh` o lê
  para decidir a próxima versão.
- A área é onde a mudança vive: `auth`, `vehicles`, `records`,
  `reminders`, `dashboard`, `import`, `settings`, `users`, `ui`, `db`,
  `docker`, `release`. Omita apenas quando não houver um único lugar.
- O número da issue vai no final: `fix(records): keep photos on edit (#12)`.
- Releases: `chore(release): 0.4.0`.

O corpo é opcional e curto: por que a mudança existe, nunca o que o diff já
diz. Acima de 100 palavras, o detalhe pertence ao README ou ao changelog, ou o
commit pede divisão. **Cada parágrafo do corpo é uma linha, não quebrado:** o
GitHub preserva cada quebra de linha do corpo, então texto quebrado em 72
colunas quebra uma segunda vez em um celular. Escreva com `git commit -F -` e
um heredoc.

Sem travessões (em dashes) em mensagens de commit: dois-pontos, vírgula ou
ponto final no lugar deles.

`tools/git-hooks/commit-msg` recusa linhas de atribuição, travessões, assunto
sem tipo e assunto ou corpo longos demais. `pre-push` recusa publicar qualquer
commit ou tag com atribuição. `pre-commit` recusa `CLAUDE.md` e `.claude/`,
que são apenas locais: listados em `.git/info/exclude`, nunca commitados.

## Versões

Toda release segue [Semantic Versioning 2.0.0](https://semver.org/). Para um
app, a "API pública" é qualquer coisa da qual uma instalação existente dependa:
o volume de dados, a configuração, as URLs e os recursos.

| Incremento | Quando | Exemplos |
| --- | --- | --- |
| **MAJOR** | Qualquer coisa que uma instalação existente não aguente sem ajuda | Uma migração que uma versão antiga não consegue ler de volta; um recurso ou configuração removido; uma variável de ambiente renomeada ou removida; um caminho de volume ou porta alterado |
| **MINOR** | Funcionalidade nova e retrocompatível, ou uma depreciação | Um novo recurso, configuração ou página; uma nova variável de ambiente opcional |
| **PATCH** | Apenas correções retrocompatíveis | Uma correção de bug, uma correção de desempenho, uma correção de segurança sem mudança de comportamento |

`tools/next-version.sh --why` lê os tipos de Conventional Commit desde a
última release e diz qual incremento eles pedem: `!` ou um rodapé
`BREAKING CHANGE:` é major, `feat` é minor, `fix`, `perf` e `revert` são patch.
Ele não consegue ver tudo, então leia também os commits: um `fix` que muda o
schema de forma irreversível ainda é MAJOR.

**Antes de qualquer release, diga claramente se a versão pedida não se encaixa**
no que os commits desde a última tag contêm, e o que o SemVer pede no lugar. O
mantenedor decide; um desencontro precisa ser uma decisão, não um acidente. Uma
release sem recursos é um patch. Uma versão nunca conta para trás, e uma
versão lançada nunca é reutilizada.

## Lançamento (releasing)

1. Adicione a entrada da versão ao changelog em `templates/index.html`
   (é o que a seção About mostra), escrita do ponto de vista do usuário.
2. `tools/prepare-release.sh [VERSION]`: confere a versão contra
   `tools/next-version.sh` (recusando desencontro, a menos que `FORCE_VERSION=1`),
   a define em `app.py`, `Dockerfile` e `README.md`, commita
   `chore(release): X.Y.Z` e cria a tag `vX.Y.Z`. Nada é enviado.
3. Envie `main` e depois a tag. A tag dispara `.github/workflows/release.yml`,
   que cria a release do GitHub intitulada `vX.Y.Z`, com o corpo de
   `tools/release-notes.sh`.
4. Compile a imagem a partir da tag e envie ao Docker Hub como
   `hyprlab/garage-logbook:X.Y.Z` e `:latest`.

## Estilo de texto

Documentação, o changelog, notas de release, textos do app e respostas a issues:

- Linguagem factual e simples. Diga o que o app faz, não o que ele permite
  que você faça. Sem marketing, sem superlativos, sem emoji, sem travessões.
- Inglês americano em tudo que o app mostra: color, behavior, canceled.
- Linhas do changelog descrevem a mudança do ponto de vista do usuário. Como
  foi construído pertence ao commit.

## Créditos

Pull requests externos entram como commits em `main` feitos pelo mantenedor,
creditando o autor com um trailer que usa o endereço noreply do GitHub deles:

```
Co-Authored-By: Jane Doe <12345678+janedoe@users.noreply.github.com>
```

Obtenha o id com `gh api users/<login> --jq .id`. Um endereço tirado do
próprio commit da pessoa pode não estar vinculado à conta dela, e aí ela
nunca aparece como contribuidora; isso não pode ser corrigido depois de uma
release com tag sem reescrever o histórico. Feche o pull request com um
comentário dizendo o que foi aproveitado, o que mudou e o que ficou de fora.

Em notas de release, um `@` é para pessoas cujo código, arte ou tradução está
na release. Repórteres e solicitantes são nomeados sem o `@`: um @ notifica
alguém e parece autoria.

## Respostas a issues

Toda resposta a uma issue ou pull request escrita por um agente começa com
`*Agentic reply:*` em itálico, depois uma linha em branco, depois a resposta.

- Uma resposta dizendo que algo está pronto tem uma ou duas frases: o que
  mudou do ponto de vista do usuário, e qual versão carrega isso.
- Sem agradecimentos, sem cordialidades, sem travessões. Simples, breve, humano.
- Qualquer coisa que o usuário precise fazer é uma lista numerada, um pedido
  por item.
- Responda depois que a imagem for enviada, não antes.
