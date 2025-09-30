"""
MFN (MetroFiber) Cancellation Module
=====================================
Service cancellation automation for MetroFiber portal using Playwright via browser service.

Architecture:
    Worker → Browser Service → Firefox (Playwright)
    
This module:
- Extends MFN validation to reuse login and search logic
- Finds and clicks cancellation button
- Submits cancellation request
- Captures cancellation reference ID
- Returns standardized results
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime
import asyncio

from providers.mfn.validation import MFNValidation
from provider_factory import AutomationError

logger = logging.getLogger(__name__)


class MFNCancellation(MFNValidation):
    """MetroFiber service cancellation automation"""
    
    def __init__(self, browser_client):
        super().__init__(browser_client)
        self.cancellation_captured_id = None
    
    async def execute(self, job_id: int, parameters: Dict) -> Dict:
        """
        Execute MFN cancellation
        
        Parameters:
            - circuit_number: Service circuit number (required)
            - customer_name: Customer name (optional)
            - customer_id: Customer ID (optional)
            - fsan: FSAN (optional)
            - cancellation_reason: Reason for cancellation (optional)
        """
        self.job_id = job_id
        logger.info(f"Job {job_id}: Starting MFN cancellation")
        
        # Extract parameters
        circuit_number = parameters.get("circuit_number") or parameters.get("order_id")
        customer_name = parameters.get("customer_name", "")
        customer_id = parameters.get("customer_id", "")
        fsan = parameters.get("fsan", "")
        cancellation_reason = parameters.get("cancellation_reason", "Customer request")
        
        if not circuit_number:
            raise AutomationError("circuit_number or order_id is required")
        
        try:
            # Create browser session
            await self.create_session(job_id)
            
            # Login (inherited from validation)
            logger.info(f"Job {job_id}: Logging into MFN portal")
            await self._login()
            
            # Search for service (inherited from validation)
            logger.info(f"Job {job_id}: Searching for circuit {circuit_number}")
            service_found = await self._search_service(
                circuit_number, customer_name, customer_id, fsan
            )
            
            if not service_found:
                logger.info(f"Job {job_id}: Service not found, cannot cancel")
                return self._build_not_found_result()
            
            # Open service details
            logger.info(f"Job {job_id}: Opening service details")
            await self._open_service_details(circuit_number)
            
            # Check if already cancelled
            logger.info(f"Job {job_id}: Checking for existing cancellation")
            already_cancelled = await self._check_existing_cancellation()
            
            if already_cancelled:
                logger.info(f"Job {job_id}: Service already has pending cancellation")
                return self._build_already_cancelled_result()
            
            # Execute cancellation
            logger.info(f"Job {job_id}: Executing cancellation")
            await self._execute_cancellation(cancellation_reason)
            
            # Capture reference ID
            logger.info(f"Job {job_id}: Capturing cancellation reference")
            await self._capture_cancellation_reference()
            
            # Build result
            result = self._build_cancellation_success_result()
            
            logger.info(f"Job {job_id}: MFN cancellation completed successfully")
            return result
            
        except Exception as e:
            logger.error(f"Job {job_id}: MFN cancellation failed - {str(e)}")
            screenshot = await self.take_screenshot("error")
            raise AutomationError(f"MFN cancellation failed: {str(e)}")
        
        finally:
            await self.cleanup()
    
    async def _open_service_details(self, circuit_number: str):
        """Open service detail page"""
        try:
            # Click on service to open details
            await self.browser.click(
                self.session_id,
                f"a[data-circuit='{circuit_number}']"
            )
            await asyncio.sleep(2)
            
            # Wait for detail page
            await self.browser.wait_for_selector(
                self.session_id,
                "#service-details",
                timeout=self.WAIT_TIMEOUT
            )
            
            # Take screenshot
            screenshot = await self.take_screenshot("service_details_before_cancel")
            self.screenshots.append({
                "name": "service_details_before_cancel",
                "data": screenshot,
                "timestamp": datetime.utcnow().isoformat()
            })
            
        except Exception as e:
            raise AutomationError(f"Failed to open service details: {str(e)}")
    
    async def _check_existing_cancellation(self) -> bool:
        """Check if service already has pending cancellation"""
        try:
            # Look for cancellation indicator in the UI
            cancellation_pending = await self.browser.is_visible(
                self.session_id,
                "text='Cancellation Pending'",
                timeout=3
            )
            
            if cancellation_pending:
                return True
            
            # Check status field
            try:
                status_text = await self.browser.get_text(
                    self.session_id,
                    "#status",
                    timeout=3
                )
                if "cancel" in status_text.lower() or "pending" in status_text.lower():
                    return True
            except:
                pass
            
            return False
            
        except Exception as e:
            logger.warning(f"Error checking existing cancellation: {str(e)}")
            return False
    
    async def _execute_cancellation(self, reason: str):
        """Execute the cancellation workflow"""
        try:
            # Look for cancellation button on detail page
            # The button is typically in the action bar at the top
            cancellation_button_selectors = [
                "button#cancel-service",
                "a#cancel-service",
                "button:has-text('Cancel Service')",
                "a:has-text('Cancel Service')",
                "button.cancel-btn",
                "//button[contains(text(), 'Cancel')]"
            ]
            
            button_clicked = False
            for selector in cancellation_button_selectors:
                try:
                    button_visible = await self.browser.is_visible(
                        self.session_id,
                        selector,
                        timeout=3
                    )
                    if button_visible:
                        await self.browser.click(self.session_id, selector)
                        button_clicked = True
                        logger.info(f"Clicked cancellation button: {selector}")
                        break
                except:
                    continue
            
            if not button_clicked:
                # Try scrolling up to see the button
                await self.browser.execute_script(
                    self.session_id,
                    "window.scrollTo(0, 0)"
                )
                await asyncio.sleep(1)
                
                # Take screenshot to debug
                screenshot = await self.take_screenshot("cancellation_button_not_found")
                self.screenshots.append({
                    "name": "cancellation_button_not_found",
                    "data": screenshot,
                    "timestamp": datetime.utcnow().isoformat()
                })
                
                raise AutomationError("Could not find cancellation button")
            
            # Wait for cancellation form/modal
            await asyncio.sleep(2)
            
            # Take screenshot of cancellation form
            screenshot = await self.take_screenshot("cancellation_form")
            self.screenshots.append({
                "name": "cancellation_form",
                "data": screenshot,
                "timestamp": datetime.utcnow().isoformat()
            })
            
            # Fill cancellation reason if field exists
            try:
                reason_field_visible = await self.browser.is_visible(
                    self.session_id,
                    "textarea#cancellation_reason",
                    timeout=3
                )
                if reason_field_visible:
                    await self.browser.type_text(
                        self.session_id,
                        "textarea#cancellation_reason",
                        reason
                    )
            except:
                logger.info("No cancellation reason field found, skipping")
            
            # Click confirm/submit button
            confirm_selectors = [
                "button#confirm-cancellation",
                "button:has-text('Confirm')",
                "button:has-text('Submit')",
                "button[type='submit']"
            ]
            
            confirmed = False
            for selector in confirm_selectors:
                try:
                    button_visible = await self.browser.is_visible(
                        self.session_id,
                        selector,
                        timeout=3
                    )
                    if button_visible:
                        await self.browser.click(self.session_id, selector)
                        confirmed = True
                        logger.info(f"Clicked confirm button: {selector}")
                        break
                except:
                    continue
            
            if not confirmed:
                raise AutomationError("Could not find confirmation button")
            
            # Wait for submission to complete
            await asyncio.sleep(3)
            
            # Take screenshot after submission
            screenshot = await self.take_screenshot("after_cancellation_submit")
            self.screenshots.append({
                "name": "after_cancellation_submit",
                "data": screenshot,
                "timestamp": datetime.utcnow().isoformat()
            })
            
        except Exception as e:
            raise AutomationError(f"Failed to execute cancellation: {str(e)}")
    
    async def _capture_cancellation_reference(self):
        """Capture cancellation reference ID from confirmation"""
        try:
            # Look for success message with reference ID
            reference_selectors = [
                "#cancellation-reference",
                ".cancellation-id",
                "text='Reference:'",
                "text='Cancellation ID:'"
            ]
            
            for selector in reference_selectors:
                try:
                    ref_text = await self.browser.get_text(
                        self.session_id,
                        selector,
                        timeout=3
                    )
                    if ref_text:
                        # Extract ID from text (might be "Reference: 12345" or similar)
                        import re
                        match = re.search(r'\d+', ref_text)
                        if match:
                            self.cancellation_captured_id = match.group(0)
                            logger.info(f"Captured cancellation ID: {self.cancellation_captured_id}")
                            return
                except:
                    continue
            
            # If no reference found, try to get it from history
            logger.info("No reference ID in confirmation, checking history")
            await self._check_cancellation_in_history()
            
        except Exception as e:
            logger.warning(f"Failed to capture cancellation reference: {str(e)}")
            # Not critical - cancellation may still have succeeded
    
    async def _check_cancellation_in_history(self):
        """Check history for the newly created cancellation record"""
        try:
            # Navigate back to service details if needed
            current_url = await self.browser.get_current_url(self.session_id)
            if "customerDetail" not in current_url:
                # Need to return to main and search again
                logger.info("Returning to main to check history")
                await self.browser.navigate(
                    self.session_id,
                    f"{self.PORTAL_URL}main.php"
                )
            
            # Click history button
            await self.browser.click(self.session_id, "button#history")
            await asyncio.sleep(2)
            
            # Look for most recent cancellation record
            history_rows = await self.browser.query_all(
                self.session_id,
                "table#history-table tbody tr"
            )
            
            # Check first row (most recent)
            if history_rows:
                first_row_text = history_rows[0].get("text", "").lower()
                if "cancellation" in first_row_text and "captured" in first_row_text:
                    # Try to extract ID
                    import re
                    match = re.search(r'\d+', first_row_text)
                    if match:
                        self.cancellation_captured_id = match.group(0)
                        logger.info(f"Found cancellation ID in history: {self.cancellation_captured_id}")
            
            # Take screenshot
            screenshot = await self.take_screenshot("history_after_cancellation")
            self.screenshots.append({
                "name": "history_after_cancellation",
                "data": screenshot,
                "timestamp": datetime.utcnow().isoformat()
            })
            
        except Exception as e:
            logger.warning(f"Failed to check history: {str(e)}")
    
    def _build_cancellation_success_result(self) -> Dict:
        """Build successful cancellation result"""
        return {
            "status": "success",
            "message": "Service cancellation submitted successfully",
            "found": True,
            "cancellation_submitted": True,
            "cancellation_captured_id": self.cancellation_captured_id,
            "pending_cease_order": True,
            "evidence": {
                "screenshots": self.screenshots
            }
        }
    
    def _build_already_cancelled_result(self) -> Dict:
        """Build result when service is already cancelled"""
        return {
            "status": "success",
            "message": "Service already has pending cancellation",
            "found": True,
            "cancellation_submitted": False,
            "already_cancelled": True,
            "pending_cease_order": True,
            "evidence": {
                "screenshots": self.screenshots
            }
        }
    
    def _build_not_found_result(self) -> Dict:
        """Build not found result"""
        return {
            "status": "error",
            "message": "Service not found, cannot cancel",
            "found": False,
            "cancellation_submitted": False,
            "evidence": {
                "screenshots": self.screenshots
            }
        }
