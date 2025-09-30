# Provider Refactoring Guide
## Converting Selenium to Browser Service with Tab Management

This guide shows how to refactor existing provider modules (like Octotel) to use the browser service instead of local Selenium.

---

## Pattern Overview

### **Keep the Same Structure:**
```
providers/
├── octotel/
│   ├── __init__.py
│   ├── validation.py          # Keep this structure
│   └── cancellation.py         # Keep this structure
├── openserve/                  # Renamed from 'osn'
│   ├── __init__.py
│   ├── validation.py
│   └── cancellation.py
└── ...
```

### **Each Module Contains:**
1. **Pydantic Models** - Data validation (ValidationRequest, ServiceData, etc.)
2. **Service Classes** - ScreenshotService, DataProcessor, etc.
3. **Main Automation Class** - OctotelValidationAutomation
4. **Execute Function** - Entry point called by worker

---

## Key Changes Required

### **1. Remove Local BrowserService Class**

**BEFORE (Selenium):**
```python
class BrowserService:
    def __init__(self):
        self.driver: Optional[webdriver.Chrome] = None
    
    def create_driver(self, job_id: str) -> webdriver.Chrome:
        options = ChromeOptions()
        options.add_argument('--headless')
        service = Service(executable_path=Config.CHROMEDRIVER_PATH)
        self.driver = webdriver.Chrome(service=service, options=options)
        return self.driver
    
    def cleanup(self):
        if self.driver:
            self.driver.quit()
```

**AFTER (Browser Service):**
```python
# Remove BrowserService class entirely
# Browser session management handled by browser_client
```

---

### **2. Update Main Automation Class**

**BEFORE:**
```python
class OctotelValidationAutomation:
    def __init__(self):
        self.browser_service = None
        self.driver = None
        self.screenshot_service = None
    
    def _setup_services(self, job_id: str):
        self.browser_service = BrowserService()
        self.driver = self.browser_service.create_driver(job_id)
        self.screenshot_service = ScreenshotService(job_id)
    
    def validate_circuit(self, request: ValidationRequest):
        self._setup_services(request.job_id)
        # ... automation logic ...
        self._cleanup_services()
```

**AFTER:**
```python
class OctotelValidationAutomation:
    def __init__(self, browser_client: BrowserServiceClient):
        self.browser = browser_client  # Injected dependency
        self.session_id = None
        self.screenshot_service = None
    
    async def validate_circuit(self, request: ValidationRequest):
        """Main method with tab management"""
        try:
            # Create browser session
            self.session_id = await self.browser.create_session(
                int(request.job_id), 
                headless=True
            )
            
            # Setup services
            self.screenshot_service = ScreenshotService(request.job_id)
            
            # Execute automation
            result = await self._execute_automation(request)
            
            return result
            
        finally:
            # Always cleanup
            if self.session_id:
                await self.browser.close_session(self.session_id)
```

---

### **3. Convert Selenium Calls to Browser Service**

#### **Navigation**
```python
# BEFORE
self.driver.get("https://portal.com")

# AFTER
await self.browser.navigate(
    self.session_id, 
    "https://portal.com",
    wait_until="networkidle"
)
```

#### **Finding and Clicking Elements**
```python
# BEFORE
element = self.driver.find_element(By.ID, "login-button")
element.click()

# AFTER
await self.browser.click(self.session_id, "#login-button")
```

#### **Typing Text**
```python
# BEFORE
username_field = self.driver.find_element(By.ID, "username")
username_field.clear()
username_field.send_keys("myuser")

# AFTER
await self.browser.type_text(
    self.session_id,
    "#username",
    "myuser",
    clear=True
)
```

#### **Waiting for Elements**
```python
# BEFORE
wait = WebDriverWait(self.driver, 15)
element = wait.until(EC.presence_of_element_located((By.ID, "results")))

# AFTER
await self.browser.wait_for_selector(
    self.session_id,
    "#results",
    timeout=15
)
```

#### **Getting Text**
```python
# BEFORE
text = element.text

# AFTER
text = await self.browser.get_text(self.session_id, "#element-id")
```

#### **Screenshots**
```python
# BEFORE
self.driver.save_screenshot(filepath)

# AFTER
screenshot_b64 = await self.browser.screenshot(
    self.session_id,
    full_page=True
)
```

#### **Executing JavaScript**
```python
# BEFORE
result = self.driver.execute_script("return document.title;")

# AFTER
result = await self.browser.execute_script(
    self.session_id,
    "return document.title;"
)
```

---

### **4. Update ScreenshotService**

**BEFORE:**
```python
class ScreenshotService:
    def take_screenshot(self, driver: webdriver.Chrome, name: str):
        filepath = self.evidence_dir / f"{name}.png"
        driver.save_screenshot(str(filepath))
        
        with open(filepath, 'rb') as f:
            screenshot_data = base64.b64encode(f.read()).decode()
        
        return ScreenshotData(name=name, data=screenshot_data, ...)
```

**AFTER:**
```python
class ScreenshotService:
    async def take_screenshot(self, browser_client: BrowserServiceClient,
                             session_id: str, name: str):
        # Get screenshot from browser service (already base64)
        screenshot_b64 = await browser_client.screenshot(
            session_id,
            full_page=True
        )
        
        # Save to file
        filepath = self.evidence_dir / f"{name}.png"
        screenshot_bytes = base64.b64decode(screenshot_b64)
        with open(filepath, 'wb') as f:
            f.write(screenshot_bytes)
        
        return ScreenshotData(name=name, data=screenshot_b64, ...)
```

---

### **5. Update Execute Function**

**BEFORE:**
```python
def execute(parameters: Dict[str, Any]) -> Dict[str, Any]:
    request = ValidationRequest(
        job_id=parameters.get("job_id"),
        circuit_number=parameters.get("circuit_number")
    )
    
    automation = OctotelValidationAutomation()  # No dependencies
    result = automation.validate_circuit(request)
    
    return convert_to_dict(result)
```

**AFTER:**
```python
async def execute(parameters: Dict[str, Any], 
                 browser_client: BrowserServiceClient) -> Dict[str, Any]:
    """Execute function receives browser_client from worker"""
    
    request = ValidationRequest(
        job_id=parameters.get("job_id"),
        circuit_number=parameters.get("circuit_number"),
        totp_code=parameters.get("totp_code")  # From orchestrator
    )
    
    # Inject browser_client dependency
    automation = OctotelValidationAutomation(browser_client)
    
    # Execute (note: now async)
    result = await automation.validate_circuit(request)
    
    return convert_to_dict(result)
```

---

### **6. Add Tab Management**

The browser service handles tab isolation automatically, but you can make it explicit:

```python
async def validate_circuit(self, request: ValidationRequest):
    try:
        # Create session (new browser context)
        self.session_id = await self.browser.create_session(
            int(request.job_id),
            headless=True
        )
        
        # At this point we're in a fresh browser context
        # (equivalent to opening a new incognito window)
        
        # Save original URL
        self.original_url = await self.browser.get_current_url(self.session_id)
        
        # Do automation work
        await self._login()
        await self._search()
        await self._extract_data()
        
        # Return results
        return result
        
    finally:
        # Close session (closes all tabs)
        if self.session_id:
            await self.browser.close_session(self.session_id)
```

**Key Points:**
- Each `create_session()` creates an isolated browser context
- Think of it like opening a new incognito window
- `close_session()` cleans up everything
- No need to manually manage tabs - the context IS the isolation

---

### **7. Handle TOTP from Orchestrator**

**BEFORE (Generated locally):**
```python
def handle_totp(self, driver):
    totp = pyotp.TOTP(Config.OCTOTEL_TOTP_SECRET)
    totp_code = totp.now()  # Generate locally
    
    totp_element = driver.find_element(By.ID, "totpCodeInput")
    totp_element.send_keys(totp_code)
```

**AFTER (Received from orchestrator):**
```python
async def _handle_totp(self, totp_code: Optional[str]):
    """Use TOTP code from orchestrator"""
    if not totp_code:
        # Fallback: generate locally if not provided
        import pyotp
        totp = pyotp.TOTP(Config.OCTOTEL_TOTP_SECRET)
        totp_code = totp.now()
        logger.warning("Generated TOTP locally - orchestrator should provide this")
    
    await self.browser.type_text(
        self.session_id,
        "#totpCodeInput",
        totp_code
    )
    await self.browser.click(self.session_id, "#signInButton")
```

---

## Complete Example: Refactored Octotel Validation

```python
"""
Octotel Validation - Browser Service Version
"""
import asyncio
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from browser_client import BrowserServiceClient
from config import Config

class ValidationRequest(BaseModel):
    job_id: str
    circuit_number: str
    totp_code: Optional[str] = None

class OctotelValidationAutomation:
    """Main automation using browser service"""
    
    def __init__(self, browser_client: BrowserServiceClient):
        self.browser = browser_client
        self.session_id = None
    
    async def validate_circuit(self, request: ValidationRequest) -> Dict:
        try:
            # Create session
            self.session_id = await self.browser.create_session(
                int(request.job_id), headless=True
            )
            
            # Login
            await self._login(request.totp_code)
            
            # Navigate to services
            await self.browser.click(
                self.session_id,
                "div.navbar li:nth-of-type(2) > a"
            )
            await asyncio.sleep(3)
            
            # Search
            await self.browser.type_text(
                self.session_id,
                "#search",
                request.circuit_number,
                clear=True
            )
            await self.browser.press_key(self.session_id, "Enter")
            await asyncio.sleep(5)
            
            # Extract results
            results = await self._extract_results()
            
            return {
                "status": "success",
                "found": len(results) > 0,
                "data": results
            }
            
        finally:
            if self.session_id:
                await self.browser.close_session(self.session_id)
    
    async def _login(self, totp_code: Optional[str]):
        """Login with TOTP"""
        await self.browser.navigate(
            self.session_id,
            Config.OCTOTEL_URL,
            wait_until="networkidle"
        )
        
        # Click login
        await self.browser.click(
            self.session_id,
            "//a[contains(text(), 'Login')]"
        )
        
        # Enter credentials
        await self.browser.type_text(
            self.session_id,
            "#signInFormUsername",
            Config.OCTOTEL_USERNAME
        )
        await self.browser.type_text(
            self.session_id,
            "#signInFormPassword",
            Config.OCTOTEL_PASSWORD
        )
        
        # Submit
        await self.browser.click(
            self.session_id,
            "button[name='signInSubmitButton']"
        )
        
        # TOTP
        if totp_code:
            await self.browser.wait_for_selector(
                self.session_id,
                "#totpCodeInput",
                timeout=12
            )
            await self.browser.type_text(
                self.session_id,
                "#totpCodeInput",
                totp_code
            )
            await self.browser.click(
                self.session_id,
                "#signInButton"
            )
        
        # Wait for dashboard
        await self.browser.wait_for_selector(
            self.session_id,
            "div.navbar",
            timeout=20
        )
    
    async def _extract_results(self) -> list:
        """Extract results from page"""
        # Get table text
        table_text = await self.browser.get_text(
            self.session_id,
            "table"
        )
        
        # Process results (simplified)
        return [{"raw_text": table_text}]

async def execute(parameters: Dict[str, Any], 
                 browser_client: BrowserServiceClient) -> Dict[str, Any]:
    """Entry point for worker"""
    request = ValidationRequest(
        job_id=parameters.get("job_id"),
        circuit_number=parameters.get("circuit_number"),
        totp_code=parameters.get("totp_code")
    )
    
    automation = OctotelValidationAutomation(browser_client)
    result = await automation.validate_circuit(request)
    
    return result
```

---

## Rename OSN to Openserve

**Find and replace across all files:**

```bash
# In file names
mv providers/osn/ providers/openserve/

# In code
# OSN -> Openserve
# osn -> openserve
# OSNValidation -> OpenserveValidation
# OSNCancellation -> OpenserveCancellation
```

**Example:**
```python
# BEFORE
class OSNValidation(BaseAutomation):
    PORTAL_URL = os.getenv("OPENSERVE_URL")

# AFTER
class OpenserveValidation(BaseAutomation):
    PORTAL_URL = os.getenv("OPENSERVE_URL")
```

---

## Checklist for Each Provider

- [ ] Remove local `BrowserService` class
- [ ] Update main automation class to accept `browser_client` in `__init__`
- [ ] Convert all Selenium calls to `browser_client` methods
- [ ] Make all methods `async`
- [ ] Update `execute()` function to be `async` and accept `browser_client`
- [ ] Use TOTP from `parameters["totp_code"]` instead of generating locally
- [ ] Update screenshot service to use browser_client
- [ ] Add proper session management (create/close)
- [ ] Update error handling for async operations
- [ ] Test with browser service running

---

## Summary of Changes

| Component | Before (Selenium) | After (Browser Service) |
|-----------|------------------|-------------------------|
| Browser | Local Chrome driver | Remote Firefox via REST API |
| Sync/Async | Synchronous | Async/await |
| Session Mgmt | Create/quit driver | Create/close session |
| Elements | find_element() | Selectors via REST |
| Clicks | element.click() | await browser.click() |
| Text Input | send_keys() | await browser.type_text() |
| Wait | WebDriverWait | await browser.wait_for_selector() |
| Screenshots | save_screenshot() | await browser.screenshot() |
| TOTP | Generate locally | Receive from orchestrator |
| Dependencies | WebDriver, Selenium | BrowserServiceClient |
| Cleanup | driver.quit() | await close_session() |

---

## Next Steps

1. **Start with one provider** (e.g., Octotel validation)
2. **Test thoroughly** with browser service running
3. **Refactor remaining providers** using same pattern
4. **Update factory** to pass browser_client to execute()
5. **Deploy and validate** end-to-end flow
