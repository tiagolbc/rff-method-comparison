# Publicação no GitHub — passo a passo

## Nome recomendado

`rff-method-comparison`

## Opção A — GitHub CLI

Abra o Git Bash ou PowerShell dentro da pasta do projeto e execute:

```bash
git init -b main
git add .
git status
git commit -m "Release RFF Method Comparison v25.0.0"
gh auth login
gh repo create tiagolbc/rff-method-comparison --public --source=. --remote=origin --push
```

## Opção B — Git e site do GitHub

1. No GitHub, crie um repositório vazio chamado `rff-method-comparison`.
2. Não marque as opções para criar README, `.gitignore` ou licença, pois esses arquivos já estão no pacote.
3. Abra o Git Bash dentro da pasta do projeto.
4. Execute:

```bash
git init -b main
git add .
git status
git commit -m "Release RFF Method Comparison v25.0.0"
git remote add origin https://github.com/tiagolbc/rff-method-comparison.git
git remote -v
git push -u origin main
```

## Antes de enviar

Confira o resultado de:

```bash
git status --short
git ls-files
```

Não devem aparecer arquivos de áudio, planilhas de participantes, tabelas ROI reais, pastas de resultados nem chaves/senhas.

## Criar a primeira release

No GitHub:

1. Abra **Releases**.
2. Clique em **Draft a new release**.
3. Crie a tag `v25.0.0` apontando para `main`.
4. Use o título `RFF Method Comparison v25.0.0`.
5. Cole o conteúdo de `RELEASE_NOTES_v25.0.0.md`.
6. Publique a release.

Pela GitHub CLI:

```bash
gh release create v25.0.0 --title "RFF Method Comparison v25.0.0" --notes-file RELEASE_NOTES_v25.0.0.md
```

## Depois da publicação

1. Substitua o campo `repository-code` em `CITATION.cff` pela URL definitiva, caso o nome seja diferente.
2. Faça commit e push da correção.
3. Use **Cite this repository** para conferir a citação gerada.
4. Acrescente a URL do repositório e da release ao manuscrito.
