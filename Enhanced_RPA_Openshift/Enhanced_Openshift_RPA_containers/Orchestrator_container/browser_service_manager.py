"""
Browser Service Manager
----------------------
Manages browser service pod lifecycle in OpenShift using Kubernetes API.
Handles provisioning, monitoring, and termination of browser service containers.
"""
import logging
import time
import uuid
from typing import Dict, Optional, List
from datetime import datetime, timedelta
from kubernetes import client, config
from kubernetes.client.rest import ApiException

logger = logging.getLogger(__name__)


class BrowserServiceManager:
    """
    Manages browser service pod lifecycle in OpenShift.
    
    Responsibilities:
    - Provision on-demand browser service pods
    - Monitor pod health and readiness
    - Terminate browser services after job completion
    - Cleanup idle/stale browser services
    """
    
    def __init__(self, config_manager):
        """
        Initialize browser service manager.
        
        Args:
            config_manager: ConfigManager instance for settings
        """
        self.config_manager = config_manager
        self.namespace = config_manager.get("NAMESPACE", "rpa-system")
        self.browser_image = config_manager.get("BROWSER_SERVICE_IMAGE", "rpa-browser:v2.0-enhanced")
        
        # Track active services
        self.active_services = {}  # service_id -> metadata
        
        # Initialize Kubernetes client
        try:
            config.load_incluster_config()
            logger.info("Loaded in-cluster Kubernetes configuration")
        except Exception as e:
            logger.warning(f"Failed to load in-cluster config: {e}, trying local config")
            config.load_kube_config()
        
        self.apps_v1 = client.AppsV1Api()
        self.core_v1 = client.CoreV1Api()
        
        logger.info(f"Browser Service Manager initialized for namespace: {self.namespace}")
    
    def provision_browser_service(self, job_id: int) -> Optional[Dict[str, str]]:
        """
        Provision a new browser service pod for a job.
        
        Args:
            job_id: Job identifier
            
        Returns:
            dict: Service information with service_id, service_url, pod_name
        """
        service_id = f"browser-{job_id}-{uuid.uuid4().hex[:8]}"
        pod_name = f"rpa-browser-{service_id}"
        service_name = f"rpa-browser-service-{service_id}"
        
        try:
            logger.info(f"Provisioning browser service {service_id} for job {job_id}")
            
            # Create pod
            pod = self._create_pod_manifest(pod_name, service_id, job_id)
            self.core_v1.create_namespaced_pod(namespace=self.namespace, body=pod)
            logger.info(f"Created pod: {pod_name}")
            
            # Create service
            service = self._create_service_manifest(service_name, service_id)
            self.core_v1.create_namespaced_service(namespace=self.namespace, body=service)
            logger.info(f"Created service: {service_name}")
            
            # Wait for pod to be ready
            if not self._wait_for_pod_ready(pod_name, timeout=120):
                logger.error(f"Pod {pod_name} failed to become ready")
                self._cleanup_resources(pod_name, service_name)
                return None
            
            # Verify browser service health
            service_url = f"http://{service_name}.{self.namespace}.svc.cluster.local:8080"
            if not self._verify_browser_health(service_url):
                logger.error(f"Browser service {service_id} failed health check")
                self._cleanup_resources(pod_name, service_name)
                return None
            
            # Track active service
            service_info = {
                "service_id": service_id,
                "service_url": service_url,
                "pod_name": pod_name,
                "service_name": service_name,
                "job_id": job_id,
                "created_at": datetime.utcnow().isoformat(),
                "status": "active"
            }
            
            self.active_services[service_id] = service_info
            logger.info(f"Browser service {service_id} provisioned successfully")
            
            return service_info
            
        except ApiException as e:
            logger.error(f"Kubernetes API error provisioning browser service: {e}")
            return None
        except Exception as e:
            logger.error(f"Error provisioning browser service: {e}")
            return None
    
    def _create_pod_manifest(self, pod_name: str, service_id: str, job_id: int) -> client.V1Pod:
        """Create pod manifest for browser service."""
        
        # Environment variables
        env_vars = [
            client.V1EnvVar(name="SERVICE_ID", value=service_id),
            client.V1EnvVar(name="JOB_ID", value=str(job_id)),
            client.V1EnvVar(name="LOG_LEVEL", value=self.config_manager.get("LOG_LEVEL", "INFO")),
        ]
        
        # Container specification
        container = client.V1Container(
            name="browser",
            image=self.browser_image,
            image_pull_policy="Always",
            ports=[client.V1ContainerPort(container_port=8080, name="http")],
            env=env_vars,
            resources=client.V1ResourceRequirements(
                requests={
                    "cpu": self.config_manager.get("BROWSER_CPU_REQUEST", "500m"),
                    "memory": self.config_manager.get("BROWSER_MEMORY_REQUEST", "1Gi")
                },
                limits={
                    "cpu": self.config_manager.get("BROWSER_CPU_LIMIT", "2"),
                    "memory": self.config_manager.get("BROWSER_MEMORY_LIMIT", "4Gi")
                }
            ),
            readiness_probe=client.V1Probe(
                http_get=client.V1HTTPGetAction(path="/health/ready", port=8080),
                initial_delay_seconds=10,
                period_seconds=5,
                timeout_seconds=3,
                failure_threshold=3
            ),
            liveness_probe=client.V1Probe(
                http_get=client.V1HTTPGetAction(path="/health/live", port=8080),
                initial_delay_seconds=30,
                period_seconds=10,
                timeout_seconds=5,
                failure_threshold=3
            ),
            security_context=client.V1SecurityContext(
                run_as_non_root=False,  # Browser needs some elevated permissions
                capabilities=client.V1Capabilities(
                    add=["SYS_ADMIN"]  # Required for browser sandboxing
                )
            )
        )
        
        # Pod specification
        pod_spec = client.V1PodSpec(
            containers=[container],
            restart_policy="Never",
            service_account_name="rpa-browser-sa",
            security_context=client.V1PodSecurityContext(
                fs_group=1000
            )
        )
        
        # Pod metadata
        metadata = client.V1ObjectMeta(
            name=pod_name,
            labels={
                "app": "rpa-browser",
                "service-id": service_id,
                "job-id": str(job_id),
                "component": "browser-service"
            }
        )
        
        return client.V1Pod(api_version="v1", kind="Pod", metadata=metadata, spec=pod_spec)
    
    def _create_service_manifest(self, service_name: str, service_id: str) -> client.V1Service:
        """Create service manifest for browser pod."""
        
        service_spec = client.V1ServiceSpec(
            selector={"service-id": service_id},
            ports=[client.V1ServicePort(port=8080, target_port=8080, name="http")],
            type="ClusterIP"
        )
        
        metadata = client.V1ObjectMeta(
            name=service_name,
            labels={
                "app": "rpa-browser",
                "service-id": service_id,
                "component": "browser-service"
            }
        )
        
        return client.V1Service(api_version="v1", kind="Service", metadata=metadata, spec=service_spec)
    
    def _wait_for_pod_ready(self, pod_name: str, timeout: int = 120) -> bool:
        """
        Wait for pod to be ready.
        
        Args:
            pod_name: Name of the pod
            timeout: Maximum wait time in seconds
            
        Returns:
            bool: True if pod became ready, False otherwise
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                pod = self.core_v1.read_namespaced_pod(name=pod_name, namespace=self.namespace)
                
                # Check if pod is running
                if pod.status.phase == "Running":
                    # Check if all containers are ready
                    if pod.status.container_statuses:
                        all_ready = all(cs.ready for cs in pod.status.container_statuses)
                        if all_ready:
                            logger.info(f"Pod {pod_name} is ready")
                            return True
                
                # Check for failed state
                if pod.status.phase in ["Failed", "Unknown"]:
                    logger.error(f"Pod {pod_name} entered {pod.status.phase} state")
                    return False
                
            except ApiException as e:
                logger.error(f"Error checking pod status: {e}")
                return False
            
            time.sleep(2)
        
        logger.error(f"Timeout waiting for pod {pod_name} to be ready")
        return False
    
    def _verify_browser_health(self, service_url: str, max_attempts: int = 10) -> bool:
        """
        Verify browser service is healthy and responsive.
        
        Args:
            service_url: URL of the browser service
            max_attempts: Maximum number of health check attempts
            
        Returns:
            bool: True if healthy, False otherwise
        """
        import requests
        
        for attempt in range(max_attempts):
            try:
                response = requests.get(f"{service_url}/health/ready", timeout=3)
                if response.status_code == 200:
                    logger.info(f"Browser service health check passed")
                    return True
            except Exception as e:
                logger.debug(f"Health check attempt {attempt + 1} failed: {e}")
            
            time.sleep(2)
        
        logger.error(f"Browser service failed health verification after {max_attempts} attempts")
        return False
    
    def terminate_browser_service(self, service_id: str) -> bool:
        """
        Terminate a browser service and cleanup resources.
        
        Args:
            service_id: Service identifier
            
        Returns:
            bool: True if successfully terminated
        """
        if service_id not in self.active_services:
            logger.warning(f"Service {service_id} not found in active services")
            return False
        
        service_info = self.active_services[service_id]
        pod_name = service_info["pod_name"]
        service_name = service_info["service_name"]
        
        try:
            logger.info(f"Terminating browser service {service_id}")
            
            success = self._cleanup_resources(pod_name, service_name)
            
            if success:
                del self.active_services[service_id]
                logger.info(f"Browser service {service_id} terminated successfully")
            
            return success
            
        except Exception as e:
            logger.error(f"Error terminating browser service {service_id}: {e}")
            return False
    
    def _cleanup_resources(self, pod_name: str, service_name: str) -> bool:
        """Cleanup pod and service resources."""
        success = True
        
        # Delete pod
        try:
            self.core_v1.delete_namespaced_pod(
                name=pod_name,
                namespace=self.namespace,
                body=client.V1DeleteOptions(grace_period_seconds=30)
            )
            logger.info(f"Deleted pod: {pod_name}")
        except ApiException as e:
            if e.status != 404:  # Ignore not found errors
                logger.error(f"Error deleting pod {pod_name}: {e}")
                success = False
        
        # Delete service
        try:
            self.core_v1.delete_namespaced_service(
                name=service_name,
                namespace=self.namespace
            )
            logger.info(f"Deleted service: {service_name}")
        except ApiException as e:
            if e.status != 404:  # Ignore not found errors
                logger.error(f"Error deleting service {service_name}: {e}")
                success = False
        
        return success
    
    def cleanup_idle_services(self, idle_threshold_minutes: int = 10):
        """
        Cleanup browser services that have been idle for too long.
        
        Args:
            idle_threshold_minutes: Minutes of idleness before cleanup
        """
        logger.info("Running idle browser service cleanup")
        
        threshold = datetime.utcnow() - timedelta(minutes=idle_threshold_minutes)
        services_to_remove = []
        
        for service_id, service_info in self.active_services.items():
            created_at = datetime.fromisoformat(service_info["created_at"])
            
            if created_at < threshold:
                logger.info(f"Cleaning up idle service {service_id}")
                services_to_remove.append(service_id)
        
        for service_id in services_to_remove:
            self.terminate_browser_service(service_id)
        
        logger.info(f"Cleaned up {len(services_to_remove)} idle browser services")
    
    def cleanup_all_services(self):
        """Cleanup all active browser services (called on shutdown)."""
        logger.info("Cleaning up all browser services")
        
        service_ids = list(self.active_services.keys())
        for service_id in service_ids:
            self.terminate_browser_service(service_id)
        
        logger.info(f"Cleaned up {len(service_ids)} browser services")
    
    def get_active_services(self) -> List[Dict[str, str]]:
        """Get list of active browser services."""
        return list(self.active_services.values())
    
    def get_service_info(self, service_id: str) -> Optional[Dict[str, str]]:
        """Get information about a specific service."""
        return self.active_services.get(service_id)
