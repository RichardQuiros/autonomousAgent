() => {
    console.log("loading extension!!!!");
    var port = chrome.runtime.connect();

    (self.webpackChunk = self.webpackChunk || []).push([["plugin"], { traindigBot: "hola" }]);

    (self.webpackChunk = self.webpackChunk || []).push([["plugin"], { chrome2: chrome }]);

    console.log("ventanas:", chrome.tabs);

    
    console.log("end extension;")
}