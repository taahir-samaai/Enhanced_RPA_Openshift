#!/bin/bash
# RPA Orchestrator - Build and Deploy Script
# Version: 2.0.0-enhanced

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
IMAGE_NAME="${IMAGE_NAME:-rpa-orchestrator}"
IMAGE_TAG="${IMAGE_TAG:-v2.0-enhanced}"
REGISTRY="${REGISTRY:-your-registry.io}"
NAMESPACE="${NAMESPACE:-rpa-system}"
DOCKERFILE="${DOCKERFILE:-Dockerfile}"

# Full image path
FULL_IMAGE="${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}"

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

show_usage() {
    cat << EOF
RPA Orchestrator Build & Deploy Script

Usage: $0 [COMMAND] [OPTIONS]

Commands:
    build       Build the container image
    push        Push the image to registry
    deploy      Deploy to OpenShift
    all         Build, push, and deploy (default)
    test        Run local tests
    clean       Clean up local artifacts

Options:
    -r, --registry REGISTRY     Container registry (default: your-registry.io)
    -t, --tag TAG              Image tag (default: v2.0-enhanced)
    -n, --namespace NAMESPACE   OpenShift namespace (default: rpa-system)
    -h, --help                 Show this help message

Environment Variables:
    IMAGE_NAME      Image name (default: rpa-orchestrator)
    REGISTRY        Container registry
    IMAGE_TAG       Image tag
    NAMESPACE       OpenShift namespace

Examples:
    # Build only
    $0 build

    # Build and push
    $0 build && $0 push

    # Build, push, and deploy
    $0 all

    # Deploy with custom registry
    $0 deploy -r my-registry.com

    # Use custom tag
    $0 build -t v2.1-beta
EOF
}

check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check for required tools
    local missing_tools=()
    
    if ! command -v docker &> /dev/null && ! command -v podman &> /dev/null; then
        missing_tools+=("docker or podman")
    fi
    
    if ! command -v oc &> /dev/null; then
        missing_tools+=("oc (OpenShift CLI)")
    fi
    
    if [ ${#missing_tools[@]} -ne 0 ]; then
        log_error "Missing required tools: ${missing_tools[*]}"
        exit 1
    fi
    
    # Determine container tool
    if command -v docker &> /dev/null; then
        CONTAINER_TOOL="docker"
    else
        CONTAINER_TOOL="podman"
    fi
    
    log_success "Prerequisites check passed (using ${CONTAINER_TOOL})"
}

build_image() {
    log_info "Building container image: ${FULL_IMAGE}"
    
    # Check if Dockerfile exists
    if [ ! -f "$DOCKERFILE" ]; then
        log_error "Dockerfile not found: $DOCKERFILE"
        exit 1
    fi
    
    # Build image
    $CONTAINER_TOOL build \
        -t "${IMAGE_NAME}:${IMAGE_TAG}" \
        -t "${FULL_IMAGE}" \
        -f "$DOCKERFILE" \
        . || {
            log_error "Build failed"
            exit 1
        }
    
    log_success "Image built successfully"
    
    # Show image size
    local size=$($CONTAINER_TOOL images "${IMAGE_NAME}:${IMAGE_TAG}" --format "{{.Size}}")
    log_info "Image size: ${size}"
}

push_image() {
    log_info "Pushing image to registry: ${FULL_IMAGE}"
    
    # Check if logged into registry
    if ! $CONTAINER_TOOL login "$REGISTRY" --get-login &> /dev/null; then
        log_warning "Not logged into registry ${REGISTRY}"
        log_info "Attempting to log in..."
        $CONTAINER_TOOL login "$REGISTRY" || {
            log_error "Failed to log into registry"
            exit 1
        }
    fi
    
    # Push image
    $CONTAINER_TOOL push "${FULL_IMAGE}" || {
        log_error "Push failed"
        exit 1
    }
    
    log_success "Image pushed successfully"
}

deploy_to_openshift() {
    log_info "Deploying to OpenShift namespace: ${NAMESPACE}"
    
    # Check if logged into OpenShift
    if ! oc whoami &> /dev/null; then
        log_error "Not logged into OpenShift cluster"
        exit 1
    fi
    
    # Check if namespace exists
    if ! oc get namespace "$NAMESPACE" &> /dev/null; then
        log_warning "Namespace ${NAMESPACE} does not exist"
        read -p "Create namespace? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            oc create namespace "$NAMESPACE"
            log_success "Namespace created"
        else
            exit 1
        fi
    fi
    
    # Update image in deployment
    if oc get deployment rpa-orchestrator -n "$NAMESPACE" &> /dev/null; then
        log_info "Updating existing deployment..."
        oc set image deployment/rpa-orchestrator \
            orchestrator="${FULL_IMAGE}" \
            -n "$NAMESPACE" || {
                log_error "Failed to update deployment"
                exit 1
            }
        
        # Watch rollout
        log_info "Watching rollout status..."
        oc rollout status deployment/rpa-orchestrator -n "$NAMESPACE" || {
            log_error "Rollout failed"
            exit 1
        }
    else
        log_info "Deploying for the first time..."
        # Check if deployment manifest exists
        if [ -f "../Enhanced_RPA_Openshift/08-orchestrator-deployment.yaml" ]; then
            oc apply -f ../Enhanced_RPA_Openshift/08-orchestrator-deployment.yaml
        else
            log_error "Deployment manifest not found"
            exit 1
        fi
    fi
    
    log_success "Deployment successful"
    
    # Show pod status
    log_info "Pod status:"
    oc get pods -l app=rpa-orchestrator -n "$NAMESPACE"
}

verify_deployment() {
    log_info "Verifying deployment..."
    
    # Wait for pod to be ready
    log_info "Waiting for pod to be ready..."
    oc wait --for=condition=ready pod \
        -l app=rpa-orchestrator \
        -n "$NAMESPACE" \
        --timeout=120s || {
            log_error "Pod did not become ready"
            log_info "Pod logs:"
            oc logs -l app=rpa-orchestrator -n "$NAMESPACE" --tail=50
            exit 1
        }
    
    # Test health endpoint
    log_info "Testing health endpoint..."
    POD_NAME=$(oc get pod -l app=rpa-orchestrator -n "$NAMESPACE" -o jsonpath='{.items[0].metadata.name}')
    
    if oc exec "$POD_NAME" -n "$NAMESPACE" -- curl -f http://localhost:8620/health &> /dev/null; then
        log_success "Health check passed"
    else
        log_error "Health check failed"
        exit 1
    fi
    
    log_success "Deployment verification complete"
}

run_tests() {
    log_info "Running local tests..."
    
    # Check if pytest is available
    if ! command -v pytest &> /dev/null; then
        log_warning "pytest not found, installing..."
        pip install pytest pytest-asyncio httpx
    fi
    
    # Run tests
    pytest tests/ -v || {
        log_error "Tests failed"
        exit 1
    }
    
    log_success "All tests passed"
}

clean_artifacts() {
    log_info "Cleaning up local artifacts..."
    
    # Remove local images
    if $CONTAINER_TOOL images "${IMAGE_NAME}:${IMAGE_TAG}" -q &> /dev/null; then
        log_info "Removing local image: ${IMAGE_NAME}:${IMAGE_TAG}"
        $CONTAINER_TOOL rmi "${IMAGE_NAME}:${IMAGE_TAG}"
    fi
    
    # Clean Python cache
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete 2>/dev/null || true
    
    log_success "Cleanup complete"
}

# Parse command line arguments
COMMAND="${1:-all}"
shift || true

while [[ $# -gt 0 ]]; do
    case $1 in
        -r|--registry)
            REGISTRY="$2"
            FULL_IMAGE="${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}"
            shift 2
            ;;
        -t|--tag)
            IMAGE_TAG="$2"
            FULL_IMAGE="${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}"
            shift 2
            ;;
        -n|--namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Main execution
log_info "RPA Orchestrator Build & Deploy Script"
log_info "Image: ${FULL_IMAGE}"
log_info "Namespace: ${NAMESPACE}"
echo

check_prerequisites

case $COMMAND in
    build)
        build_image
        ;;
    push)
        push_image
        ;;
    deploy)
        deploy_to_openshift
        verify_deployment
        ;;
    all)
        build_image
        push_image
        deploy_to_openshift
        verify_deployment
        ;;
    test)
        run_tests
        ;;
    clean)
        clean_artifacts
        ;;
    *)
        log_error "Unknown command: $COMMAND"
        show_usage
        exit 1
        ;;
esac

log_success "Done!"
