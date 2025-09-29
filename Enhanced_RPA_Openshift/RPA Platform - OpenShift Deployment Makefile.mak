# RPA Platform - OpenShift Deployment Makefile
# Version: v2.0-enhanced

.PHONY: help deploy deploy-dev deploy-staging deploy-prod clean validate health-check logs backup restore

# Default target
.DEFAULT_GOAL := help

# Variables
NAMESPACE_DEV := rpa-system-dev
NAMESPACE_STAGING := rpa-system-staging
NAMESPACE_PROD := rpa-system
KUSTOMIZE := kubectl kustomize
KUBECTL := oc
TIMEOUT := 300s

# Colors for output
RED := \033[0;31m
GREEN := \033[0;32m
YELLOW := \033[0;33m
BLUE := \033[0;34m
NC := \033[0m # No Color

##@ General

help: ## Display this help message
	@echo "$(BLUE)RPA Platform - OpenShift Deployment$(NC)"
	@echo ""
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make $(CYAN)<target>$(NC)\n"} /^[a-zA-Z_0-9-]+:.*?##/ { printf "  $(CYAN)%-20s$(NC) %s\n", $$1, $$2 } /^##@/ { printf "\n$(YELLOW)%s$(NC)\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

##@ Validation

validate: ## Validate all YAML files
	@echo "$(BLUE)Validating YAML files...$(NC)"
	@for file in *.yaml; do \
		echo "Validating $$file..."; \
		$(KUBECTL) apply --dry-run=client -f $$file > /dev/null && echo "$(GREEN)✓ $$file$(NC)" || echo "$(RED)✗ $$file$(NC)"; \
	done
	@echo "$(GREEN)Validation complete$(NC)"

validate-kustomize: ## Validate Kustomize configurations
	@echo "$(BLUE)Validating Kustomize configurations...$(NC)"
	@$(KUSTOMIZE) build overlays/dev > /dev/null && echo "$(GREEN)✓ Dev overlay$(NC)" || echo "$(RED)✗ Dev overlay$(NC)"
	@$(KUSTOMIZE) build overlays/staging > /dev/null && echo "$(GREEN)✓ Staging overlay$(NC)" || echo "$(RED)✗ Staging overlay$(NC)"
	@$(KUSTOMIZE) build overlays/production > /dev/null && echo "$(GREEN)✓ Production overlay$(NC)" || echo "$(RED)✗ Production overlay$(NC)"
	@echo "$(GREEN)Kustomize validation complete$(NC)"

check-secrets: ## Check if secrets are properly configured
	@echo "$(BLUE)Checking secret configuration...$(NC)"
	@if grep -q "REPLACE_WITH_ACTUAL_" 02-secrets.yaml; then \
		echo "$(RED)✗ Secrets still contain placeholder values!$(NC)"; \
		echo "$(YELLOW)Please update 02-secrets.yaml before deploying$(NC)"; \
		exit 1; \
	else \
		echo "$(GREEN)✓ Secrets appear to be configured$(NC)"; \
	fi

##@ Deployment

deploy-dev: check-secrets ## Deploy to development environment
	@echo "$(BLUE)Deploying to development environment...$(NC)"
	$(KUBECTL) apply -k overlays/dev/
	@echo "$(YELLOW)Waiting for pods to be ready...$(NC)"
	$(KUBECTL) wait --for=condition=ready pod -l app=rpa-orchestrator -n $(NAMESPACE_DEV) --timeout=$(TIMEOUT) || true
	$(KUBECTL) wait --for=condition=ready pod -l app=rpa-worker -n $(NAMESPACE_DEV) --timeout=$(TIMEOUT) || true
	@echo "$(GREEN)Development deployment complete$(NC)"
	@make -s health-check-dev

deploy-staging: check-secrets validate ## Deploy to staging environment
	@echo "$(BLUE)Deploying to staging environment...$(NC)"
	$(KUBECTL) apply -k overlays/staging/
	@echo "$(YELLOW)Waiting for pods to be ready...$(NC)"
	$(KUBECTL) wait --for=condition=ready pod -l app=rpa-orchestrator -n $(NAMESPACE_STAGING) --timeout=$(TIMEOUT) || true
	$(KUBECTL) wait --for=condition=ready pod -l app=rpa-worker -n $(NAMESPACE_STAGING) --timeout=$(TIMEOUT) || true
	@echo "$(GREEN)Staging deployment complete$(NC)"
	@make -s health-check-staging

deploy-prod: check-secrets validate ## Deploy to production environment (requires confirmation)
	@echo "$(RED)⚠️  WARNING: This will deploy to PRODUCTION$(NC)"
	@echo "$(YELLOW)Press Ctrl+C to cancel, or Enter to continue...$(NC)"
	@read confirm
	@echo "$(BLUE)Deploying to production environment...$(NC)"
	$(KUBECTL) apply -k overlays/production/
	@echo "$(YELLOW)Waiting for pods to be ready...$(NC)"
	$(KUBECTL) wait --for=condition=ready pod -l app=rpa-orchestrator -n $(NAMESPACE_PROD) --timeout=$(TIMEOUT) || true
	$(KUBECTL) wait --for=condition=ready pod -l app=rpa-worker -n $(NAMESPACE_PROD) --timeout=$(TIMEOUT) || true
	@echo "$(GREEN)Production deployment complete$(NC)"
	@make -s health-check-prod

deploy: deploy-dev ## Alias for deploy-dev

##@ Health Checks

health-check-dev: ## Check health of development environment
	@echo "$(BLUE)Checking development environment health...$(NC)"
	@echo "\n$(YELLOW)Pod Status:$(NC)"
	@$(KUBECTL) get pods -n $(NAMESPACE_DEV) -o wide || true
	@echo "\n$(YELLOW)Service Status:$(NC)"
	@$(KUBECTL) get svc -n $(NAMESPACE_DEV) || true
	@echo "\n$(YELLOW)Recent Events:$(NC)"
	@$(KUBECTL) get events -n $(NAMESPACE_DEV) --sort-by='.lastTimestamp' | tail -10 || true

health-check-staging: ## Check health of staging environment
	@echo "$(BLUE)Checking staging environment health...$(NC)"
	@echo "\n$(YELLOW)Pod Status:$(NC)"
	@$(KUBECTL) get pods -n $(NAMESPACE_STAGING) -o wide || true
	@echo "\n$(YELLOW)Service Status:$(NC)"
	@$(KUBECTL) get svc -n $(NAMESPACE_STAGING) || true

health-check-prod: ## Check health of production environment
	@echo "$(BLUE)Checking production environment health...$(NC)"
	@echo "\n$(YELLOW)Pod Status:$(NC)"
	@$(KUBECTL) get pods -n $(NAMESPACE_PROD) -o wide || true
	@echo "\n$(YELLOW)Service Status:$(NC)"
	@$(KUBECTL) get svc -n $(NAMESPACE_PROD) || true
	@echo "\n$(YELLOW)HPA Status:$(NC)"
	@$(KUBECTL) get hpa -n $(NAMESPACE_PROD) || true

health-check: health-check-dev ## Alias for health-check-dev

##@ Logs

logs-orchestrator: ## Tail orchestrator logs (dev)
	$(KUBECTL) logs -f deployment/rpa-orchestrator -n $(NAMESPACE_DEV) --tail=50

logs-orchestrator-prod: ## Tail orchestrator logs (prod)
	$(KUBECTL) logs -f deployment/rpa-orchestrator -n $(NAMESPACE_PROD) --tail=50

logs-worker: ## Tail worker logs (dev)
	$(KUBECTL) logs -f deployment/rpa-worker -n $(NAMESPACE_DEV) --tail=50

logs-worker-prod: ## Tail worker logs (prod)
	$(KUBECTL) logs -f deployment/rpa-worker -n $(NAMESPACE_PROD) --tail=50

logs-browser: ## Tail browser service logs (dev)
	@POD=$$($(KUBECTL) get pod -l app=rpa-browser -n $(NAMESPACE_DEV) -o jsonpath='{.items[0].metadata.name}' 2>/dev/null) && \
	if [ -n "$$POD" ]; then \
		$(KUBECTL) logs -f $$POD -n $(NAMESPACE_DEV); \
	else \
		echo "$(YELLOW)No browser service pods found$(NC)"; \
	fi

logs-valkey: ## Tail Valkey logs (dev)
	$(KUBECTL) logs -f valkey-0 -n $(NAMESPACE_DEV)

##@ Maintenance

backup: ## Run manual Valkey backup
	@echo "$(BLUE)Starting manual Valkey backup...$(NC)"
	$(KUBECTL) create job --from=cronjob/valkey-backup manual-backup-$$(date +%Y%m%d%H%M%S) -n $(NAMESPACE_PROD)
	@echo "$(GREEN)Backup job created$(NC)"

cleanup-evidence: ## Run manual evidence cleanup
	@echo "$(BLUE)Starting evidence cleanup...$(NC)"
	$(KUBECTL) create job --from=cronjob/evidence-cleanup manual-cleanup-$$(date +%Y%m%d%H%M%S) -n $(NAMESPACE_PROD)
	@echo "$(GREEN)Cleanup job created$(NC)"

restart-orchestrator: ## Restart orchestrator deployment
	@echo "$(BLUE)Restarting orchestrator...$(NC)"
	$(KUBECTL) rollout restart deployment/rpa-orchestrator -n $(NAMESPACE_PROD)
	$(KUBECTL) rollout status deployment/rpa-orchestrator -n $(NAMESPACE_PROD)
	@echo "$(GREEN)Orchestrator restarted$(NC)"

restart-workers: ## Restart worker deployment
	@echo "$(BLUE)Restarting workers...$(NC)"
	$(KUBECTL) rollout restart deployment/rpa-worker -n $(NAMESPACE_PROD)
	$(KUBECTL) rollout status deployment/rpa-worker -n $(NAMESPACE_PROD)
	@echo "$(GREEN)Workers restarted$(NC)"

scale-workers: ## Scale workers (usage: make scale-workers REPLICAS=10)
	@if [ -z "$(REPLICAS)" ]; then \
		echo "$(RED)Error: REPLICAS not specified$(NC)"; \
		echo "Usage: make scale-workers REPLICAS=10"; \
		exit 1; \
	fi
	@echo "$(BLUE)Scaling workers to $(REPLICAS) replicas...$(NC)"
	$(KUBECTL) scale deployment/rpa-worker --replicas=$(REPLICAS) -n $(NAMESPACE_PROD)
	@echo "$(GREEN)Workers scaled$(NC)"

##@ Rollback

rollback-orchestrator: ## Rollback orchestrator to previous version
	@echo "$(RED)Rolling back orchestrator...$(NC)"
	$(KUBECTL) rollout undo deployment/rpa-orchestrator -n $(NAMESPACE_PROD)
	$(KUBECTL) rollout status deployment/rpa-orchestrator -n $(NAMESPACE_PROD)
	@echo "$(GREEN)Orchestrator rolled back$(NC)"

rollback-workers: ## Rollback workers to previous version
	@echo "$(RED)Rolling back workers...$(NC)"
	$(KUBECTL) rollout undo deployment/rpa-worker -n $(NAMESPACE_PROD)
	$(KUBECTL) rollout status deployment/rpa-worker -n $(NAMESPACE_PROD)
	@echo "$(GREEN)Workers rolled back$(NC)"

##@ Cleanup

clean-dev: ## Delete development environment
	@echo "$(RED)Deleting development environment...$(NC)"
	@echo "$(YELLOW)Press Ctrl+C to cancel, or Enter to continue...$(NC)"
	@read confirm
	$(KUBECTL) delete namespace $(NAMESPACE_DEV)
	@echo "$(GREEN)Development environment deleted$(NC)"

clean-staging: ## Delete staging environment
	@echo "$(RED)Deleting staging environment...$(NC)"
	@echo "$(YELLOW)Press Ctrl+C to cancel, or Enter to continue...$(NC)"
	@read confirm
	$(KUBECTL) delete namespace $(NAMESPACE_STAGING)
	@echo "$(GREEN)Staging environment deleted$(NC)"

clean-prod: ## Delete production environment (DANGEROUS!)
	@echo "$(RED)⚠️  DANGER: This will delete PRODUCTION!$(NC)"
	@echo "$(YELLOW)Type 'DELETE-PRODUCTION' to confirm:$(NC)"
	@read confirm && [ "$$confirm" = "DELETE-PRODUCTION" ] || exit 1
	$(KUBECTL) delete namespace $(NAMESPACE_PROD)
	@echo "$(GREEN)Production environment deleted$(NC)"

clean: clean-dev ## Alias for clean-dev

##@ Troubleshooting

debug-orchestrator: ## Get detailed orchestrator pod info
	@POD=$$($(KUBECTL) get pod -l app=rpa-orchestrator -n $(NAMESPACE_DEV) -o jsonpath='{.items[0].metadata.name}') && \
	echo "$(BLUE)Pod: $$POD$(NC)" && \
	$(KUBECTL) describe pod $$POD -n $(NAMESPACE_DEV)

debug-worker: ## Get detailed worker pod info
	@POD=$$($(KUBECTL) get pod -l app=rpa-worker -n $(NAMESPACE_DEV) -o jsonpath='{.items[0].metadata.name}') && \
	echo "$(BLUE)Pod: $$POD$(NC)" && \
	$(KUBECTL) describe pod $$POD -n $(NAMESPACE_DEV)

debug-valkey: ## Get Valkey cluster status
	@echo "$(BLUE)Valkey Cluster Status:$(NC)"
	@$(KUBECTL) exec -it valkey-0 -n $(NAMESPACE_DEV) -- valkey-cli -a "$$($(KUBECTL) get secret valkey-credentials -n $(NAMESPACE_DEV) -o jsonpath='{.data.password}' | base64 -d)" INFO replication || echo "$(RED)Failed to connect to Valkey$(NC)"

test-connectivity: ## Test connectivity between components
	@echo "$(BLUE)Testing connectivity...$(NC)"
	@echo "\n$(YELLOW)Orchestrator -> Valkey:$(NC)"
	@ORCH_POD=$$($(KUBECTL) get pod -l app=rpa-orchestrator -n $(NAMESPACE_DEV) -o jsonpath='{.items[0].metadata.name}') && \
	$(KUBECTL) exec $$ORCH_POD -n $(NAMESPACE_DEV) -- nc -zv valkey-service 6379 || true
	@echo "\n$(YELLOW)Worker -> Orchestrator:$(NC)"
	@WORKER_POD=$$($(KUBECTL) get pod -l app=rpa-worker -n $(NAMESPACE_DEV) -o jsonpath='{.items[0].metadata.name}') && \
	$(KUBECTL) exec $$WORKER_POD -n $(NAMESPACE_DEV) -- nc -zv rpa-orchestrator-service 8620 || true

port-forward: ## Port forward orchestrator API to localhost:8620
	@echo "$(BLUE)Port forwarding orchestrator API to localhost:8620...$(NC)"
	@echo "$(YELLOW)Access at: http://localhost:8620$(NC)"
	@echo "$(YELLOW)Press Ctrl+C to stop$(NC)"
	$(KUBECTL) port-forward svc/rpa-orchestrator-service 8620:8620 -n $(NAMESPACE_DEV)

##@ Information

status: ## Show deployment status
	@echo "$(BLUE)RPA Platform Status$(NC)\n"
	@echo "$(YELLOW)Development:$(NC)"
	@$(KUBECTL) get pods -n $(NAMESPACE_DEV) 2>/dev/null | grep -E "NAME|rpa-|valkey" || echo "Not deployed"
	@echo "\n$(YELLOW)Staging:$(NC)"
	@$(KUBECTL) get pods -n $(NAMESPACE_STAGING) 2>/dev/null | grep -E "NAME|rpa-|valkey" || echo "Not deployed"
	@echo "\n$(YELLOW)Production:$(NC)"
	@$(KUBECTL) get pods -n $(NAMESPACE_PROD) 2>/dev/null | grep -E "NAME|rpa-|valkey" || echo "Not deployed"

version: ## Show version information
	@echo "$(BLUE)RPA Platform Version Information$(NC)"
	@echo "Deployment Version: v2.0-enhanced"
	@echo "Deployment Date: 2025-09-29"
	@echo "Architecture: Three-Layer Enhanced"
	@echo ""
	@echo "$(YELLOW)Tool Versions:$(NC)"
	@$(KUBECTL) version --client || true
	@kustomize version || echo "kustomize: not installed separately"

docs: ## Open deployment documentation
	@if command -v xdg-open > /dev/null; then \
		xdg-open 00-DEPLOYMENT-GUIDE.md; \
	elif command -v open > /dev/null; then \
		open 00-DEPLOYMENT-GUIDE.md; \
	else \
		cat 00-DEPLOYMENT-GUIDE.md; \
	fi
