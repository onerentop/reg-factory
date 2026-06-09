"""反检测 Stealth 脚本。从 common/browser.py 完整迁移。"""


STEALTH_JS = r"""
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
    try { delete navigator.__proto__.webdriver; } catch(e) {}

    if (!window.chrome) {
        window.chrome = {runtime: {}, loadTimes: function(){}, csi: function(){}, app: {}};
    }

    const origQuery = window.navigator.permissions?.query;
    if (origQuery) {
        window.navigator.permissions.query = (params) => (
            params.name === 'notifications' ?
                Promise.resolve({state: Notification.permission}) :
                origQuery(params)
        );
    }

    Object.defineProperty(navigator, 'plugins', {
        get: () => [
            {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format', length: 1},
            {name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '', length: 1},
            {name: 'Native Client', filename: 'internal-nacl-plugin', description: '', length: 1},
        ],
    });

    Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});

    if (navigator.connection) {
        Object.defineProperty(navigator.connection, 'rtt', {get: () => 50});
    }

    Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
    Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});

    const cdcProps = Object.getOwnPropertyNames(window).filter(p =>
        p.match(/^cdc_|^__cdc|^_cdp|^__cdp|^chrome_devtools/i)
    );
    cdcProps.forEach(p => { try { delete window[p]; } catch(e) {} });

    const origPrepare = Error.prepareStackTrace;
    Error.prepareStackTrace = function(err, stack) {
        const filtered = stack.filter(s => {
            const fn = s.getFunctionName() || '';
            const file = s.getFileName() || '';
            return !fn.includes('cdp') && !file.includes('pptr') &&
                   !file.includes('playwright') && !file.includes('puppeteer');
        });
        if (origPrepare) return origPrepare(err, filtered);
        return err + '\n' + filtered.map(s => '    at ' + s).join('\n');
    };

    const origDefineProperty = Object.defineProperty;
    Object.defineProperty = function(obj, prop, desc) {
        if (obj === window && typeof prop === 'string' &&
            (prop.startsWith('cdc_') || prop.startsWith('__cdc'))) {
            return obj;
        }
        return origDefineProperty.call(this, obj, prop, desc);
    };

    if (window.outerWidth === 0) {
        Object.defineProperty(window, 'outerWidth', {get: () => window.innerWidth + 16});
    }
    if (window.outerHeight === 0) {
        Object.defineProperty(window, 'outerHeight', {get: () => window.innerHeight + 88});
    }

    if (Notification.permission === 'denied') {
        Object.defineProperty(Notification, 'permission', {get: () => 'default'});
    }

    const origGetter = Object.getOwnPropertyDescriptor(HTMLIFrameElement.prototype, 'contentWindow');
    if (origGetter) {
        Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {
            get: function() {
                const w = origGetter.get.call(this);
                if (w) {
                    try { Object.defineProperty(w.navigator, 'webdriver', {get: () => undefined}); } catch(e) {}
                }
                return w;
            }
        });
    }
"""


class StealthInjector:
    """Stealth 注入器。三重保险注入反检测脚本。"""

    def __init__(self, custom_script: str | None = None):
        self._script = custom_script or STEALTH_JS

    @property
    def script(self) -> str:
        return self._script

    async def inject(self, context, page) -> None:
        try:
            cdp = await context.new_cdp_session(page)
            await cdp.send("Page.addScriptToEvaluateOnNewDocument", {"source": self._script})
        except Exception:
            pass
        try:
            await page.evaluate(f"() => {{{self._script}}}")
        except Exception:
            pass
        try:
            await context.add_init_script(f"() => {{{self._script}}}")
        except Exception:
            pass
