const pendingResponses = [];

async function init() {
  setBotSetting();
  await captureTabs();
}

async function captureTabs() {
  const targets = await chrome.debugger.getTargets();
  this.botSetting.websites.forEach(website => setTarget(targets, website));
  
  this.botSetting.websites.forEach(website => {
    website.TABS.forEach(async tab => {
      await attachTab(tab.id);
    });
  });

  addDebugListener();
}

function setTarget(targets, website) {
  targets.forEach((target, index) => {
    if (target.url.startsWith(website.URL)) {
      website.TABS.push({ id: target.tabId, title: target.title, commands: website.COMMANDS });
      targets.splice(index, 1);
    }
  });
}

async function attachTab(tabId) {
  await chrome.debugger.attach({ tabId }, '1.3', () => {
    chrome.debugger.sendCommand(
      { tabId: tabId },
      'Network.enable',
      {}
    );
  });
}

async function addDebugListener() {
  await chrome.debugger.onEvent.addListener((source, method, params) => {
    if (method.includes('Network.')) {
      onNetwork(source, method, params);
    } else if (method.includes('childNodeCountUpdated')) {
      //onNodeChange(source.tabId, params.nodeId);
    }
  })
}

function onNetwork(source, method, params) {
  const { requestId } = params;
  if (requestId >= 0 && method === 'Network.loadingFinished') {
    chrome.debugger.sendCommand(source, 'Network.getResponseBody', { requestId }, (result) => {
      if (typeof result?.body === 'string' && result.body.startsWith('event')) {
        const resp = parseSSE(result.body.replaceAll('finished_successfully', ''));
        console.log('SSE Response:', resp);
         for (const r of pendingResponses) r(resp?.message);
        pendingResponses.length = 0;
      }
    });
  }
}

async function sendCommand(tab, command) {
  await chrome.debugger.sendCommand(
    { tabId: tab.id },
    'Page.addScriptToEvaluateOnNewDocument',
    { source: command, runImmediately: true }
  );
}

function setBotSetting() {
  this.botSetting = {
    websites: [{
      NAME: 'Chatgpt',
      COMMANDS: {
        POST: `document.querySelector("#prompt-textarea > p").innerHTML="?";setTimeout(() => {
          document.querySelector("#composer-submit-button").click();
        }, 200);`,
        RELOAD: `location.reload();`,
      },
      URL: 'https://chatgpt.com/',
      TABS: []
    }],
    nodes: [],
  }
}
