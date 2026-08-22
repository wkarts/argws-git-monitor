from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import EncryptionService
from app.models.github import GitHubConnection, Repository
from app.models.platform import ActionClass, ClinicAnalysis, ClinicFinding, FindingSeverity
from app.services.ghcr_service import GhcrService
from app.services.github_client import GitHubAPIError, GitHubClient
from app.services.github_management import GitHubManagementService

CATEGORY_MAX = {"branches":20,"releases":20,"ci_cd":20,"repository_size":15,"security":15,"maintenance":10}

class ClinicError(RuntimeError): pass

def finding(category:str,severity:str,action_class:str,code:str,title:str,description:str,evidence:dict[str,Any],risk:str,recommendation:str,action_available:str|None=None)->dict[str,Any]:
    return {"category":category,"severity":severity,"action_class":action_class,"code":code,"title":title,"description":description,"evidence":evidence,"risk":risk,"recommendation":recommendation,"action_available":action_available}

def parse_date(value:Any)->datetime|None:
    if not value: return None
    try: return datetime.fromisoformat(str(value).replace("Z","+00:00"))
    except ValueError: return None

async def analyze_repository(session:AsyncSession,*,user_id:uuid.UUID,repository_id:uuid.UUID,job_id:uuid.UUID|None=None,include_deep_git:bool=True,include_actions:bool=True,include_ghcr:bool=True)->ClinicAnalysis:
    repository=await session.get(Repository,repository_id)
    if not repository: raise ClinicError("Repositório não encontrado.")
    connection=await session.get(GitHubConnection,repository.connection_id)
    if not connection or connection.user_id!=user_id or not connection.token_encrypted: raise ClinicError("Conexão GitHub inválida.")
    analysis=ClinicAnalysis(user_id=user_id,repository_id=repository_id,job_id=job_id,status="running",score=0,score_breakdown={},metrics={},created_at=datetime.now(UTC)); session.add(analysis); await session.flush()
    token=EncryptionService().decrypt(connection.token_encrypted); client=GitHubClient(token,api_url=connection.api_url); scores=CATEGORY_MAX.copy(); findings:list[dict[str,Any]]=[]; now=datetime.now(UTC)
    try:
        repo=await client.get_repository(repository.full_name)
        branches=await client.list_branches(repository.full_name,limit=200)
        releases=await client.list_releases(repository.full_name,limit=100)
        tags=await client.optional_paginate("tags",f"/repos/{repository.full_name}/tags",limit=200,empty_statuses={403,404})
        tree=await GitHubManagementService(client).list_tree(repository.full_name,branch=repository.default_branch)
        workflows=await client.list_workflows(repository.full_name,limit=100) if include_actions else []
        runs=await client.list_workflow_runs(repository.full_name,limit=100) if include_actions else []
        artifacts=await client.optional_paginate("actions_artifacts",f"/repos/{repository.full_name}/actions/artifacts",limit=100,empty_statuses={403,404}) if include_actions else []

        stale=[]; merged=[]; branch_evidence=[]
        if include_deep_git:
            for item in branches[:40]:
                name=str(item.get("name") or ""); sha=str((item.get("commit") or {}).get("sha") or ""); updated=None
                if sha:
                    try:
                        commit=await client.get_json(f"/repos/{repository.full_name}/commits/{sha}"); updated=parse_date((((commit or {}).get("commit") or {}).get("committer") or {}).get("date"))
                    except GitHubAPIError: pass
                is_stale=bool(name!=repository.default_branch and updated and updated<now-timedelta(days=60)); is_merged=False
                if name and name!=repository.default_branch:
                    try:
                        cmp=await client.get_json(f"/repos/{repository.full_name}/compare/{quote(repository.default_branch,safe='')}...{quote(name,safe='')}")
                        is_merged=isinstance(cmp,dict) and int(cmp.get("ahead_by") or 0)==0 and str(cmp.get("status") or "") in {"behind","identical"}
                    except GitHubAPIError: pass
                if is_stale: stale.append(name)
                if is_merged: merged.append(name)
                branch_evidence.append({"name":name,"sha":sha,"protected":bool(item.get("protected")),"updated_at":updated.isoformat() if updated else None,"stale":is_stale,"merged_into_default":is_merged})
        if stale:
            scores["branches"]-=min(8,max(2,len(stale)//3+1)); findings.append(finding("branches",FindingSeverity.MEDIUM.value if len(stale)>5 else FindingSeverity.LOW.value,ActionClass.REVIEW.value,"branches.stale",f"{len(stale)} branch(es) sem atividade recente","Branches fora da default branch não receberam commits nos últimos 60 dias.",{"branches":[x for x in branch_evidence if x["stale"]]},"Branches antigas podem esconder trabalho abandonado.","Revisar merge/proteção antes de remover; branch não mergeada nunca é removida automaticamente.","cleanup.analyze_branches"))
        if merged:
            findings.append(finding("branches",FindingSeverity.INFORMATIONAL.value,ActionClass.REVIEW.value,"branches.merged_candidates",f"{len(merged)} branch(es) totalmente incorporadas à default","A comparação GitHub indica ahead_by=0 para essas branches.",{"branches":merged},"Podem ser candidatas à limpeza, mas regras de proteção e deployments precisam ser verificadas.","Enviar ao Cleanup Engine para dependency graph e Dry Run.","cleanup.analyze_branches"))
        if len(branches)>50: scores["branches"]-=3

        release_tags={str(x.get("tag_name") or "") for x in releases}; tag_names={str(x.get("name") or "") for x in tags}; tags_without_release=sorted(tag_names-release_tags); releases_without_assets=[x for x in releases if not x.get("assets")]
        if releases_without_assets:
            scores["releases"]-=min(6,max(1,len(releases_without_assets)//3)); findings.append(finding("releases",FindingSeverity.LOW.value,ActionClass.REVIEW.value,"releases.no_assets",f"{len(releases_without_assets)} release(s) sem assets","A API retornou releases sem arquivos anexos.",{"release_ids":[x.get("id") for x in releases_without_assets]},"Pode prejudicar distribuição quando o projeto depende de binários.","Confirmar se o projeto é source-only antes de qualquer ação."))
        if tags_without_release:
            scores["releases"]-=min(6,max(1,len(tags_without_release)//5)); findings.append(finding("releases",FindingSeverity.INFORMATIONAL.value,ActionClass.REVIEW.value,"releases.tags_without_release",f"{len(tags_without_release)} tag(s) sem GitHub Release","Tags não possuem objeto Release correspondente.",{"tags":tags_without_release[:50]},"Pode ser intencional para checkpoints técnicos.","Classificar tags estáveis, técnicas e temporárias no Cleanup Profile."))

        failed=[x for x in runs if x.get("conclusion")=="failure"]; disabled=[x for x in workflows if x.get("state") not in {None,"active"}]
        if include_actions and not workflows:
            scores["ci_cd"]-=12; findings.append(finding("ci_cd",FindingSeverity.MEDIUM.value,ActionClass.REVIEW.value,"ci.missing","Nenhum workflow GitHub Actions detectado","A API não retornou workflows ativos.",{"workflow_count":0},"Mudanças podem chegar sem CI/CD automatizado.","Confirmar se existe outro CI ou criar workflow apropriado."))
        if failed:
            scores["ci_cd"]-=min(10,max(2,len(failed)//5+2)); findings.append(finding("ci_cd",FindingSeverity.HIGH.value if len(failed)>=10 else FindingSeverity.MEDIUM.value,ActionClass.REVIEW.value,"ci.failed_runs",f"{len(failed)} run(s) com failure na amostra","Execuções recentes falharam.",{"runs":[{"id":x.get("id"),"name":x.get("name"),"head_sha":x.get("head_sha"),"url":x.get("html_url")} for x in failed[:20]]},"Pode indicar pipeline quebrado ou release inconsistente.","Corrigir causa; runs antigos só entram no Cleanup após análise."))
        if disabled:
            scores["ci_cd"]-=min(4,len(disabled)); findings.append(finding("ci_cd",FindingSeverity.LOW.value,ActionClass.REVIEW.value,"ci.disabled_workflows",f"{len(disabled)} workflow(s) não ativos","Workflows em estado diferente de active foram detectados.",{"workflows":[{"id":x.get("id"),"name":x.get("name"),"state":x.get("state")} for x in disabled]},"Automação esperada pode não executar.","Verificar se são obsoletos antes de limpar."))

        size_kb=int(repo.get("size") or 0); size_severity=None
        if size_kb>1_000_000: scores["repository_size"]-=10; size_severity=FindingSeverity.HIGH.value
        elif size_kb>500_000: scores["repository_size"]-=6; size_severity=FindingSeverity.MEDIUM.value
        elif size_kb>100_000: scores["repository_size"]-=3; size_severity=FindingSeverity.LOW.value
        large=[x for x in tree if int(x.get("size") or 0)>20*1024*1024]
        if large:
            scores["repository_size"]-=min(5,len(large)); findings.append(finding("repository_size",FindingSeverity.MEDIUM.value,ActionClass.REVIEW.value,"git.large_files",f"{len(large)} arquivo(s) acima de 20 MiB na árvore atual","Arquivos grandes foram encontrados na default branch.",{"files":large[:30]},"Binários no Git ampliam clone/backup e podem exigir LFS.","Avaliar Git LFS; reescrita de histórico somente em fluxo DESTRUCTIVE específico."))
        if size_severity: findings.append(finding("repository_size",size_severity,ActionClass.REVIEW.value,"git.repository_size","Repositório com tamanho elevado",f"A API reporta {size_kb} KiB.",{"size_kb":size_kb},"Maior custo de clone, backup e manutenção.","Analisar objetos e arquivos grandes antes de Deep Clean."))

        protected=False
        try: protected=bool(await client.get_json(f"/repos/{repository.full_name}/branches/{quote(repository.default_branch,safe='')}/protection"))
        except GitHubAPIError as exc:
            if exc.status_code not in {403,404}: raise
        if not protected:
            scores["security"]-=6; findings.append(finding("security",FindingSeverity.MEDIUM.value,ActionClass.REVIEW.value,"security.default_branch_unprotected","Default branch sem proteção detectável",f"A branch {repository.default_branch} não possui proteção consultável.",{"branch":repository.default_branch},"Force push/exclusão ou merge sem revisão podem comprometer a linha principal.","Configurar branch protection/ruleset conforme a política do projeto.","branch.configure_protection"))
        if not bool(repo.get("security_and_analysis")): scores["security"]-=2

        suspicious=[]; patterns=("node_modules/",".venv/","__pycache__/","dist/","build/",".idea/",".vscode/")
        for item in tree:
            path=str(item.get("path") or "")
            if any(path==prefix.rstrip("/") or path.startswith(prefix) for prefix in patterns): suspicious.append(path)
        if suspicious:
            scores["maintenance"]-=min(5,max(1,len(suspicious)//5)); findings.append(finding("maintenance",FindingSeverity.MEDIUM.value,ActionClass.REVIEW.value,"maintenance.generated_files","Possíveis artefatos de build/dependência versionados","Caminhos normalmente ignorados foram encontrados.",{"paths":suspicious[:100]},"Repositório cresce e diffs ficam poluídos.","Revisar .gitignore e confirmar necessidade.","files.review_gitignore"))
        if repository.archived or repository.disabled: scores["maintenance"]-=5

        ghcr_packages=[]; ghcr_versions=0; ghcr_untagged=0
        if include_ghcr:
            try:
                ghcr=GhcrService(client,connection.github_login); ghcr_packages=await ghcr.list_packages(repository.owner,limit=100); related=[x for x in ghcr_packages if repository.name.lower() in str(x.get("name") or "").lower()][:20]
                for package in related:
                    name=str(package.get("name") or "")
                    if not name: continue
                    detail=await ghcr.package_detail(repository.owner,name); versions=detail.get("versions") or []; ghcr_versions+=len(versions); ghcr_untagged+=sum(1 for x in versions if not x.get("tags"))
                if ghcr_untagged:
                    scores["maintenance"]-=min(3,max(1,ghcr_untagged//20+1)); findings.append(finding("maintenance",FindingSeverity.LOW.value,ActionClass.REVIEW.value,"ghcr.untagged_versions",f"{ghcr_untagged} versão(ões) GHCR sem tag","Packages relacionados contêm versões sem tag.",{"versions":ghcr_versions,"untagged":ghcr_untagged},"Podem consumir armazenamento, mas ainda ser referenciadas por digest.","Cruzar digest/tags com deployments no Cleanup antes de remover.","cleanup.analyze_ghcr"))
            except GitHubAPIError as exc:
                findings.append(finding("maintenance",FindingSeverity.INFORMATIONAL.value,ActionClass.REVIEW.value,"ghcr.unavailable","GHCR não pôde ser analisado","Permissão/API não permitiu consultar packages.",{"http_status":exc.status_code,"error":str(exc)},"A pontuação não penaliza recurso não observado.","Conceder packages:read para incluir GHCR."))

        scores={k:max(0,min(CATEGORY_MAX[k],v)) for k,v in scores.items()}; total=sum(scores.values())
        metrics={"repository":repository.full_name,"branches":len(branches),"stale_branches":len(stale),"merged_branch_candidates":len(merged),"releases":len(releases),"releases_without_assets":len(releases_without_assets),"tags":len(tags),"tags_without_release":len(tags_without_release),"workflows":len(workflows),"failed_runs_sample":len(failed),"artifacts_sample":len(artifacts),"repository_size_kb":size_kb,"large_files_current_tree":len(large),"default_branch_protected":protected,"suspicious_paths":len(suspicious),"ghcr_packages":len(ghcr_packages),"ghcr_versions":ghcr_versions,"ghcr_untagged_versions":ghcr_untagged,"git_lfs_detected":any(str(x.get("path") or "")==".gitattributes" for x in tree),"submodules_detected":any(str(x.get("path") or "")==".gitmodules" for x in tree)}
        for item in findings: session.add(ClinicFinding(analysis_id=analysis.id,**item))
        analysis.score=total; analysis.score_breakdown={k:{"score":scores[k],"max":CATEGORY_MAX[k]} for k in CATEGORY_MAX}; analysis.metrics=metrics; analysis.status="completed"; analysis.completed_at=datetime.now(UTC); repository.health_score=total; repository.health_status="healthy" if total>=85 else "attention" if total>=65 else "failing"; await session.flush(); return analysis
    except Exception as exc:
        analysis.status="failed"; analysis.error=str(exc); analysis.completed_at=datetime.now(UTC); await session.flush(); raise
    finally: await client.close()
