import * as crypto from "crypto";
import * as path from "path";
import * as vscode from "vscode";
import { ChildProcess, spawn } from "child_process";

type Mode = "General chat" | "Explain Code" | "Debug Assistant" | "Code Review" | "Generate Tests";
const modes: Mode[] = ["General chat", "Explain Code", "Debug Assistant", "Code Review", "Generate Tests"];
type ProposalFile = { path: string; operation: "modify" | "create"; reason: string; diff: string; previewAvailable: boolean; originalContent: string | null; proposedContent: string | null };
type Proposal = { proposalId: string; state: string; explanation: string; workspaceRoot: string; results: Array<{ path: string; status: string; detail: string }>; files: ProposalFile[] };

class Backend {
  private process: ChildProcess | undefined;
  private baseUrl = "";
  private token = crypto.randomBytes(32).toString("hex");
  private starting: Promise<void> | undefined;
  async request<T>(route: string, body?: unknown): Promise<T> {
    await this.start();
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), vscode.workspace.getConfiguration("vask").get<number>("requestTimeoutMs", 120000));
    try {
      const response = await fetch(`${this.baseUrl}/v1/${route}`, { method: body ? "POST" : "GET", headers: { "X-Vask-Token": this.token, "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined, signal: controller.signal });
      const payload = await response.json() as { error?: { message?: string } } & T;
      if (!response.ok) throw new Error(payload.error?.message || "V-Ask local service request failed.");
      return payload;
    } finally { clearTimeout(timeout); }
  }
  private async start(): Promise<void> {
    if (this.baseUrl) return;
    if (this.starting) return this.starting;
    this.starting = new Promise<void>((resolve, reject) => {
      const configured = vscode.workspace.getConfiguration("vask").get<string>("backendPath", "");
      const backendPath = configured || path.resolve(__dirname, "../../vask_service.py");
      const python = vscode.workspace.getConfiguration("vask").get<string>("pythonPath", "python");
      const child = spawn(python, [backendPath, "--port", "0", "--token", this.token], { stdio: ["ignore", "pipe", "pipe"] });
      this.process = child;
      const timer = setTimeout(() => reject(new Error("V-Ask local service did not start. Configure vask.backendPath.")), 10000);
      child.stdout?.on("data", (chunk: Buffer) => {
        const match = chunk.toString().match(/VASK_SERVICE_PORT=(\d+)/);
        if (match) { clearTimeout(timer); this.baseUrl = `http://127.0.0.1:${match[1]}`; resolve(); }
      });
      child.on("error", error => { clearTimeout(timer); this.starting = undefined; reject(error); });
      child.on("exit", code => { this.process = undefined; this.baseUrl = ""; if (!this.starting) return; clearTimeout(timer); this.starting = undefined; reject(new Error(`V-Ask local service exited (${code ?? "unknown"}).`)); });
    });
    try { await this.starting; } finally { this.starting = undefined; }
  }
  dispose(): void { this.process?.kill(); this.process = undefined; this.baseUrl = ""; }
}

class AssistantView implements vscode.WebviewViewProvider {
  private view: vscode.WebviewView | undefined;
  private mode: Mode = "General chat";
  private conversations = new Map<Mode, string>();
  private selectedFiles = new Set<string>();
  private proposals = new Map<string, Proposal>();
  constructor(private readonly extensionUri: vscode.Uri, private readonly backend: Backend) {}
  resolveWebviewView(view: vscode.WebviewView): void {
    this.view = view; view.webview.options = { enableScripts: true, localResourceRoots: [vscode.Uri.joinPath(this.extensionUri, "..", "assets")] };
    view.webview.html = this.html(view.webview);
    view.webview.onDidReceiveMessage(message => void this.receive(message));
    this.post({ type: "status", text: "Ready. Open a workspace to use project context." });
  }
  show(mode?: Mode, draft = ""): void { if (mode) this.mode = mode; void vscode.commands.executeCommand("workbench.view.extension.vask"); this.post({ type: "setMode", mode: this.mode, draft }); }
  private root(): string | undefined { return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath; }
  private post(message: unknown): void { void this.view?.webview.postMessage(message); }
  private async receive(message: unknown): Promise<void> {
    if (!message || typeof message !== "object") return;
    const data = message as { type?: unknown; text?: unknown; mode?: unknown; proposalId?: unknown; path?: unknown };
    if (typeof data.type !== "string") return;
    if (data.type === "mode" && modes.includes(data.mode as Mode)) { this.mode = data.mode as Mode; this.post({ type: "setMode", mode: this.mode }); return; }
    if (data.type === "new") {
      try { const result = await this.backend.request<{ conversationId: string }>("conversations", { mode: this.mode, fresh: true }); this.conversations.set(this.mode, result.conversationId); this.post({ type: "clear" }); }
      catch (error) { this.post({ type: "error", text: error instanceof Error ? error.message : "Could not start a conversation." }); }
      return;
    }
    if (data.type === "index") { await this.index(); return; }
    if (data.type === "preview" && typeof data.proposalId === "string" && typeof data.path === "string") { await this.preview(data.proposalId, data.path); return; }
    if ((data.type === "apply" || data.type === "reject") && typeof data.proposalId === "string") { await this.proposalAction(data.proposalId, data.type); return; }
    if ((data.type !== "send" && data.type !== "proposal") || typeof data.text !== "string" || !data.text.trim() || data.text.length > 50000) return;
    if (data.type === "proposal") { await this.createProposal(data.text.trim()); return; }
    try {
      this.post({ type: "loading", value: true });
      let conversationId = this.conversations.get(this.mode);
      if (!conversationId) {
        const current = await this.backend.request<{ conversationId: string }>("conversations", { mode: this.mode });
        conversationId = current.conversationId; this.conversations.set(this.mode, conversationId);
      }
      const result = await this.backend.request<{ conversationId: string; reply: string; context: { includedFiles: string[]; retrievedFiles: string[] } }>("chat", { mode: this.mode, message: data.text, conversationId, workspaceRoot: this.root(), selectedFiles: [...this.selectedFiles] });
      this.conversations.set(this.mode, result.conversationId);
      this.post({ type: "assistant", text: result.reply, context: result.context });
    } catch (error) { this.post({ type: "error", text: error instanceof Error ? error.message : "V-Ask request failed." }); }
    finally { this.post({ type: "loading", value: false }); }
  }
  private async createProposal(request: string): Promise<void> {
    const root = this.root();
    if (!root) { this.post({ type: "error", text: "Open a VS Code workspace before requesting a code change." }); return; }
    try {
      this.post({ type: "loading", value: true });
      const proposal = await this.backend.request<Proposal>("proposals", { workspaceRoot: root, request, selectedFiles: [...this.selectedFiles] });
      if (!this.validProposal(proposal)) throw new Error("The local service returned an invalid proposal.");
      this.proposals.set(proposal.proposalId, proposal);
      this.post({ type: "proposal", proposal });
    } catch (error) { this.post({ type: "error", text: error instanceof Error ? error.message : "Could not generate a proposal." }); }
    finally { this.post({ type: "loading", value: false }); }
  }
  private validProposal(proposal: Proposal): boolean {
    return typeof proposal?.proposalId === "string" && typeof proposal.explanation === "string" && Array.isArray(proposal.files)
      && proposal.files.length > 0 && proposal.files.length <= 5
      && proposal.files.every(file => typeof file.path === "string" && !file.path.includes("..") && typeof file.diff === "string" && typeof file.previewAvailable === "boolean");
  }
  private async preview(proposalId: string, filePath: string): Promise<void> {
    const proposal = this.proposals.get(proposalId);
    const file = proposal?.files.find(candidate => candidate.path === filePath);
    if (!proposal || !file) { this.post({ type: "error", text: "This proposal preview is no longer available. Generate it again." }); return; }
    if (!file.previewAvailable || file.originalContent === null || file.proposedContent === null) {
      this.post({ type: "error", text: `Preview for ${file.path} is too large; inspect the unified diff instead.` }); return;
    }
    const before = await vscode.workspace.openTextDocument({ content: file.originalContent });
    const after = await vscode.workspace.openTextDocument({ content: file.proposedContent });
    await vscode.commands.executeCommand("vscode.diff", before.uri, after.uri, `V-Ask proposal: ${file.path}`, { preview: true });
  }
  private async proposalAction(proposalId: string, action: "apply" | "reject"): Promise<void> {
    const proposal = this.proposals.get(proposalId);
    if (!proposal) { this.post({ type: "error", text: "This proposal is no longer available. Generate it again." }); return; }
    const root = this.root();
    if (!root) { this.post({ type: "error", text: "Open the original workspace before reviewing this proposal." }); return; }
    if (action === "apply") {
      const choice = await vscode.window.showWarningMessage(`Apply V-Ask proposal to ${proposal.files.length} file(s)?`, { modal: true }, "Apply");
      if (choice !== "Apply") return;
    }
    try {
      this.post({ type: "loading", value: true });
      const updated = await this.backend.request<Proposal>(`proposals/${proposalId}/${action}`, action === "apply" ? { workspaceRoot: root } : {});
      if (!this.validProposal(updated)) throw new Error("The local service returned an invalid proposal result.");
      this.proposals.set(proposalId, updated);
      this.post({ type: "proposal", proposal: updated });
      if (action === "apply") {
        await this.index();
        const succeeded = updated.results.filter(item => item.status === "Applied").length;
        void vscode.window.showInformationMessage(`V-Ask applied ${succeeded} of ${updated.files.length} proposed file changes.`);
      } else void vscode.window.showInformationMessage("V-Ask proposal rejected; no files were changed.");
    } catch (error) { this.post({ type: "error", text: error instanceof Error ? error.message : "Proposal action failed." }); }
    finally { this.post({ type: "loading", value: false }); }
  }
  async index(): Promise<void> {
    const root = this.root(); if (!root) { this.post({ type: "error", text: "Open a VS Code workspace before indexing project context." }); return; }
    try { const result = await this.backend.request<{ fileCount: number; skippedFiles: number }>("index", { workspaceRoot: root, refresh: true }); this.post({ type: "status", text: `Indexed ${result.fileCount} files (${result.skippedFiles} skipped).` }); }
    catch (error) { this.post({ type: "error", text: error instanceof Error ? error.message : "Indexing failed." }); }
  }
  addActiveFileToContext(): void {
    const editor = vscode.window.activeTextEditor;
    const root = this.root();
    const folder = editor ? vscode.workspace.getWorkspaceFolder(editor.document.uri) : undefined;
    if (!editor || !root || !folder || folder.uri.fsPath !== root) {
      void vscode.window.showWarningMessage("Open a file in the active V-Ask workspace before adding it as context.");
      return;
    }
    const relativePath = vscode.workspace.asRelativePath(editor.document.uri, false).replace(/\\/g, "/");
    this.selectedFiles.add(relativePath);
    this.show();
    this.post({ type: "status", text: `Added ${relativePath} to context for the next request.` });
  }
  private html(webview: vscode.Webview): string {
    const nonce = crypto.randomBytes(16).toString("hex");
    return this.reviewHtml(nonce);
    return `<!doctype html><html><head><meta charset="UTF-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-${nonce}'"><style>body{font:13px var(--vscode-font-family);color:var(--vscode-foreground);padding:10px}.brand{display:flex;gap:8px;align-items:center;border-bottom:1px solid var(--vscode-panel-border);padding-bottom:10px}.dot{width:9px;height:9px;background:#c7f464;border-radius:50%}select,textarea,button{width:100%;box-sizing:border-box;margin-top:8px;color:var(--vscode-input-foreground);background:var(--vscode-input-background);border:1px solid var(--vscode-input-border);padding:7px}button{cursor:pointer}button.primary{background:#c7f464;color:#15180d;border:0}.messages{margin-top:12px;max-height:52vh;overflow:auto}.message{white-space:pre-wrap;line-height:1.5;padding:9px 0;border-bottom:1px solid var(--vscode-panel-border)}.user{color:var(--vscode-textLink-foreground)}.status{font-size:12px;opacity:.8;margin-top:8px}.error{color:var(--vscode-errorForeground)}</style></head><body><div class="brand"><span class="dot"></span><strong>V-Ask</strong><span id="status">Local assistant</span></div><select id="mode">${modes.map(m=>`<option>${m}</option>`).join("")}</select><button id="new">New conversation</button><button id="index">Refresh project index</button><div id="messages" class="messages"></div><textarea id="input" rows="5" placeholder="Ask V-Ask… (Ctrl/Cmd+Enter to send)"></textarea><button id="send" class="primary">Send</button><script nonce="${nonce}">const vscode=acquireVsCodeApi(),q=s=>document.querySelector(s),messages=q('#messages'),input=q('#input');function add(cls,text){const d=document.createElement('div');d.className='message '+cls;d.textContent=text;messages.append(d);messages.scrollTop=messages.scrollHeight}q('#send').onclick=()=>{const text=input.value.trim();if(text){add('user',text);input.value='';vscode.postMessage({type:'send',text})}};input.onkeydown=e=>{if((e.ctrlKey||e.metaKey)&&e.key==='Enter'){e.preventDefault();q('#send').click()}};q('#mode').onchange=e=>vscode.postMessage({type:'mode',mode:e.target.value});q('#new').onclick=()=>vscode.postMessage({type:'new'});q('#index').onclick=()=>vscode.postMessage({type:'index'});window.addEventListener('message',e=>{const m=e.data;if(m.type==='assistant')add('assistant',m.text);if(m.type==='error'){q('#status').className='error';q('#status').textContent=m.text}if(m.type==='status'){q('#status').className='status';q('#status').textContent=m.text}if(m.type==='loading')q('#send').disabled=m.value;if(m.type==='setMode'){q('#mode').value=m.mode;if(m.draft)input.value=m.draft}if(m.type==='clear')messages.textContent=''})</script></body></html>`;
  }
  private reviewHtml(nonce: string): string {
    return `<!doctype html><html><head><meta charset="UTF-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-${nonce}'"><style>
body{font:13px var(--vscode-font-family);color:var(--vscode-foreground);padding:10px}.brand{display:flex;gap:8px;align-items:center;border-bottom:1px solid var(--vscode-panel-border);padding-bottom:10px}.dot{width:9px;height:9px;background:#c7f464;border-radius:50%}select,textarea,button{width:100%;box-sizing:border-box;margin-top:8px;color:var(--vscode-input-foreground);background:var(--vscode-input-background);border:1px solid var(--vscode-input-border);padding:7px}button{cursor:pointer}button.primary{background:#c7f464;color:#15180d;border:0}.button-row{display:flex;gap:7px}.button-row button{flex:1}.messages{margin-top:12px;max-height:35vh;overflow:auto}.message{white-space:pre-wrap;line-height:1.5;padding:9px 0;border-bottom:1px solid var(--vscode-panel-border)}.user{color:var(--vscode-textLink-foreground)}.status{font-size:12px;opacity:.8;margin-top:8px}.error{color:var(--vscode-errorForeground)}.proposal{margin-top:12px;border-top:1px solid var(--vscode-panel-border);padding-top:10px}.proposal h3{font-size:13px;margin:0 0 5px}.file{border-left:2px solid #c7f464;margin:8px 0;padding:0 0 0 8px}.path{font-family:var(--vscode-editor-font-family);font-weight:600}.reason{opacity:.8;margin:3px 0}.diff{font:12px var(--vscode-editor-font-family);white-space:pre;overflow:auto;max-height:220px;padding:7px;background:var(--vscode-textCodeBlock-background)}.diff .add{color:var(--vscode-testing-iconPassed)}.diff .remove{color:var(--vscode-testing-iconFailed)}.result{font-size:12px;margin-top:6px}.muted{opacity:.7;font-size:12px}
</style></head><body><div class="brand"><span class="dot"></span><strong>V-Ask</strong><span id="status">Local assistant</span></div><select id="mode">${modes.map(m=>`<option>${m}</option>`).join("")}</select><div class="button-row"><button id="new">New conversation</button><button id="index">Refresh index</button></div><div id="messages" class="messages"></div><div id="proposals"></div><textarea id="input" rows="5" placeholder="Ask V-Ask or describe a code change..."></textarea><div class="button-row"><button id="send" class="primary">Send</button><button id="propose">Propose change</button></div><script nonce="${nonce}">
const vscode=acquireVsCodeApi(),q=s=>document.querySelector(s),messages=q('#messages'),proposals=q('#proposals'),input=q('#input');
function add(cls,text){const d=document.createElement('div');d.className='message '+cls;d.textContent=text;messages.append(d);messages.scrollTop=messages.scrollHeight}
function button(label,handler){const b=document.createElement('button');b.textContent=label;b.onclick=handler;return b}
function diff(container,text){for(const line of text.split('\\n')){const row=document.createElement('div');row.textContent=line;if(line.startsWith('+')&&!line.startsWith('+++'))row.className='add';if(line.startsWith('-')&&!line.startsWith('---'))row.className='remove';container.append(row)}}
function renderProposal(p){let card=document.querySelector('[data-proposal-id="'+p.proposalId+'"]');if(card)card.remove();card=document.createElement('section');card.className='proposal';card.dataset.proposalId=p.proposalId;const title=document.createElement('h3');title.textContent='Change proposal - '+p.state;card.append(title);const explanation=document.createElement('div');explanation.textContent=p.explanation;card.append(explanation);for(const file of p.files){const section=document.createElement('div');section.className='file';const path=document.createElement('div');path.className='path';path.textContent=file.operation+' - '+file.path;section.append(path);const reason=document.createElement('div');reason.className='reason';reason.textContent=file.reason;section.append(reason);const code=document.createElement('div');code.className='diff';diff(code,file.diff||'No diff returned.');section.append(code);if(file.previewAvailable)section.append(button('Open native diff',()=>vscode.postMessage({type:'preview',proposalId:p.proposalId,path:file.path})));else{const small=document.createElement('div');small.className='muted';small.textContent='Preview is too large; inspect the unified diff above.';section.append(small)}card.append(section)}if(p.state==='Ready for review'){const actions=document.createElement('div');actions.className='button-row';actions.append(button('Apply reviewed changes',()=>vscode.postMessage({type:'apply',proposalId:p.proposalId})),button('Reject proposal',()=>vscode.postMessage({type:'reject',proposalId:p.proposalId})));card.append(actions)}for(const result of p.results||[]){const status=document.createElement('div');status.className='result';status.textContent=(result.path||'Workspace')+': '+result.status+' - '+result.detail;card.append(status)}proposals.prepend(card)}
function submit(type){const text=input.value.trim();if(text){add('user',text);input.value='';vscode.postMessage({type,text})}}q('#send').onclick=()=>submit('send');q('#propose').onclick=()=>submit('proposal');input.onkeydown=e=>{if((e.ctrlKey||e.metaKey)&&e.key==='Enter'){e.preventDefault();q('#send').click()}};q('#mode').onchange=e=>vscode.postMessage({type:'mode',mode:e.target.value});q('#new').onclick=()=>vscode.postMessage({type:'new'});q('#index').onclick=()=>vscode.postMessage({type:'index'});window.addEventListener('message',e=>{const m=e.data;if(!m||typeof m.type!=='string')return;if(m.type==='assistant')add('assistant',m.text);if(m.type==='proposal')renderProposal(m.proposal);if(m.type==='error'){q('#status').className='error';q('#status').textContent=m.text}if(m.type==='status'){q('#status').className='status';q('#status').textContent=m.text}if(m.type==='loading'){q('#send').disabled=m.value;q('#propose').disabled=m.value}if(m.type==='setMode'){q('#mode').value=m.mode;if(m.draft)input.value=m.draft}if(m.type==='clear'){messages.textContent='';proposals.textContent=''}})
</script></body></html>`;
  }
}

export function activate(context: vscode.ExtensionContext): void {
  const backend = new Backend(); const view = new AssistantView(context.extensionUri, backend);
  context.subscriptions.push(vscode.window.registerWebviewViewProvider("vask.assistant", view), { dispose: () => backend.dispose() });
  const selected = (mode: Mode) => { const editor = vscode.window.activeTextEditor; const text = editor?.document.getText(editor.selection) || editor?.document.getText() || ""; view.show(mode, text ? `Code from ${editor?.document.fileName}:\n\n\`\`\`\n${text.slice(0, 24000)}\n\`\`\`` : ""); };
  const commands: Array<[string, () => void | Thenable<void>]> = [
    ["vask.openAssistant", () => view.show()], ["vask.newConversation", () => view.show()],
    ["vask.explainSelection", () => selected("Explain Code")], ["vask.explainActiveFile", () => selected("Explain Code")],
    ["vask.debugSelection", () => selected("Debug Assistant")], ["vask.reviewSelection", () => selected("Code Review")],
    ["vask.generateTests", () => selected("Generate Tests")], ["vask.addFileToContext", () => view.addActiveFileToContext()],
    ["vask.refreshProjectIndex", () => view.index()], ["vask.openSettings", () => vscode.commands.executeCommand("workbench.action.openSettings", "@ext:vask-local.v-ask-developer-assistant")]
  ];
  for (const [id, handler] of commands) context.subscriptions.push(vscode.commands.registerCommand(id, handler));
}
export function deactivate(): void {}
