'use strict';
const $ = id => document.getElementById(id);
let importingModel=false;
let shellSyncTimer=null,shellExpectedKey=null,shellSyncDeadline=0;
const english = {
 "screenTitle": "Screen observation & interaction",
 "allowScreen": "Allow AI to see the screen",
 "screenHint": "Off by default. A tool call captures the primary screen of the computer running KiraAI and uses the session’s native multimodal or vision model. It does not operate the computer. Enable image recognition and configure a compatible model in KiraAI. Images may be retained in native multimodal conversation history.",
 "allowScreenLater": "Allow AI to schedule screen observation",
 "screenLaterHint": "Requires screen observation. AI can schedule one observation in 1–120 minutes and interact proactively. One appointment at a time; busy conversations may defer it for up to 10 minutes. Model changes, stopping or reloading cancel it. Test mode blocks proactive observation.",
 "cancelScreen": "Cancel screen appointment",
 "noScreenSchedule": "No screen appointment",
 "nextScreen": "Next observation: ",
 "selectAllResources": "Select all",
 "selectNoResources": "Deselect all",
 "addMapping": "Add mapping",
 "resetMapping": "Restore automatic mapping",
 "mappingActions": "Actions",
 "motionFile": "File",
 "motionGroup": "Group / event",
 "mappingSaveFirst": "Save this mapping before previewing it.",
 "rescanModel": "Rescan",
 "rescanDone": "Model resources refreshed; settings and drafts were preserved.",
 "outfitsTitle": "Manual outfit changes",
 "outfitsHint": "Choose expressions, motions or both for clothing. Save to use them from the desktop input or AI. Native rendering preserves wardrobe parameters. Optional events trigger replies; blank events and test mode do not.",
 "addOutfit": "Add outfit",
 "outfitName": "Outfit name",
 "outfitEvent": "AI event (optional)",
 "outfitEventHint": "For example: You changed into a white dress. Leave blank to skip AI.",
 "outfitResourceRequired": "Choose at least one expression or motion.",
 "outfitNone": "Do not use",
 "outfitUnavailable": " (unavailable)",
 "outfitInteraction": "Outfit change",
 "previewOutfit": "Preview outfit",
 "outfitPreviewSent": "Outfit preview requested. This does not save the preset or trigger AI.",
 "expandFolds": "Expand all",
 "collapseFolds": "Collapse all",
 "adaptationFold": "Model adaptation & LPK extraction",
 "connectionOptionsFold": "Remote connection & ports",
 "resourcePolicyHint": "Turn off a category or uncheck individual available items to block AI and test calls. Save per model. Disabled items remain in the table so you can enable them again. If everything is disabled, chat continues without requiring an expression or motion.",
 "allowExpressions": "Allow expressions",
 "allowMotions": "Allow motions",
 "allowDefaultExpression": "Allow restoring the default expression",
 "resourceAvailable": "Available",
 "touchPosition": "Type a location, such as head, left hand or skirt hem; leave blank for a generic click",
 "noExpressions": "No expressions enabled",
 "dragRepeat": "Allow repeated drag boundary events",
 "dragRepeatHint": "Off: each boundary fires once per gesture. On: crossing back to a boundary may fire again, subject to reply cooldown.",
 "layoutTitle": "Size & position",
 "aiLayout": "Allow AI to move and resize the model",
 "aiLayoutHint": "Off by default, saved per model. AI can move and scale the native window. Debug mode pauses layout changes.",
 "layoutBackupHint": "The first AI change saves a baseline. Restore it below; use the debug panel for manual adjustments.",
 "restoreLayout": "Restore size and position before AI adjustments",
 "layoutBridge": "",
 "layoutDisabled": "AI layout control is off",
 "layoutEnabled": "AI layout control is on",
 "expressionPreviewButton": "Preview (3s)",
 "endExpressionPreview": "End preview",
 "expressionPreviewRunning": "Previewing for 3 seconds, then restoring the previous known expression or default.",
 "expressionPreviewEnded": "Expression preview ended.",
 "motionPreviewButton": "Preview",
 "previewAppliedModel": "Preview resources of the applied model. Save connection/model changes and newly enabled resources first.",
 "preview": "Preview",
 "dragPreview": "Preview drag",
 "previewHint": "Watch the model move from minimum to maximum and return to its previous value. This does not trigger AI.",
 "originalRequested": "Original JSON model requested; automatic AI copies are now off.",
 "dragTitle": "Drag events → AI awareness",
 "dragHint": "Native parameter dragging uses the model declarations. Describe each phase for AI; blank descriptions do not trigger chat.",
 "testModeTitle": "Test mode",
 "dragBegin": "Interaction starts",
 "dragEnd": "Released",
 "dragMin": "Minimum reached",
 "dragMax": "Maximum reached",
 "dragDescription": "Describe the event for AI",
 "noInteractionEvents": "No touch or drag events received yet.",
 "touchTestMode": "Test mode (no AI)",
 "touchTestHint": "Records touch, drag and manual outfit events without starting AI replies. Use the debug panel to inspect bounds and geometry.",
 "currentExpressions": "Current expression mappings",
 "currentMotions": "Current motion mappings",
 "mappingName": "Name used by AI",
 "expressionIndex": "Expression index",
 "motionTarget": "Motion group / event / file",
 "resolvedMappingHint": "Edit the names used by AI directly, then save. Indices and playback targets are read-only and stay unchanged. Restore automatic mapping to clear this section’s edits.",
 "noResolvedMappings": "No mappings available yet.",
 "fileTarget": "File: ",
 "groupTarget": "Group/event: ",
 "resetRegion": "Clear body region",
 "observedArea": " (click observed)",
 "inferredArea": " (inferred from motion group)",
 "detectedCandidates": "Detected click area candidates",
 "motionDisconnected": "原生壳 is disconnected. Motion testing returns after reconnection.",
 "motionSyncing": "Waiting for the current model to be identified.",
 "motionUnavailable": "This model has no registered motions. Packed models may need manual mappings.",
 "modelFollowChanged": "The model changed while you were editing. Reload settings before saving; your old draft has not been applied to the new model.",
 "modelFollowReady": "Following model",
 "modelFollowWaiting": "Waiting for model synchronization",
 "touchTestActive": "Test mode active: touch detection only; AI interaction is paused.",
 "touchTestInactive": "Normal mode: clicks can trigger AI replies when click responses are enabled.",
 "touchCount": "Click",
 "mappingTitle": "Model mappings & touch regions",
 "mappingHint": "Read expressions, motions and hit areas from local Cubism JSON. Edit names used by AI; assign body regions manually.",
 "expressionMap": "Manual override: expression name → 原生壳 index",
 "expressionMapHint": "The first expression is index 0. Use the actual order in 原生壳.",
 "motionMap": "Manual override: motion name → 原生壳 group",
 "motionMapHint": "Enter a group or group:motion, such as Tap:wave. File paths shown in the automatic table are not motion group names; do not paste them here.",
 "touchMap": "Hit area → Body region",
 "touchMapHint": "Detected area names appear automatically from model declarations, click groups and observed events. Type the exact body location yourself and save. Blank locations produce ordinary clicks. Group-derived candidates require click verification; unassigned areas produce ordinary clicks.",
 "addExpression": "Add expression",
 "addMotion": "Add motion",
 "addTouch": "Add touch mapping",
 "remove": "Remove",
 "mapName": "Name / hit area",
 "mapValue": "Group or group:motion",
 "modelCounts": "Expressions / Motions / Hit areas",
 "detectedAreas": "Declared hit areas",
 "noAreas": "No areas detected yet. Click the model in test mode to discover more.",
 "noTouch": "No click received yet. Click the selected model in 原生壳.",
 "lastTouch": "Last click",
 "noAreaName": "No hit area reported",
 "noMotions": "No motions available",
 "modelChanged": "Model path changed. Previous manual mappings were cleared; save to load the new model.",
 "duplicateMap": "Mapping names must be unique within each table.",
 "voicePrompt": "Voice reply prompt",
 "voicePromptHint": "Applies only to conversations from the pet input panels. Leave empty to disable. Requires playback enabled and an available KiraAI TTS model; does not force speech on every reply.",
 "refreshing": "Refreshing…",
 "desktopStarting": "The desktop input is starting. Please wait.",
 "timeout": "Request timed out. Please try again.",
 "dismiss": "Dismiss notice",
 "openDesktop": "Open desktop input",
 "openingDesktop": "Opening…",
 "desktopOpened": "Desktop input requested on the computer running KiraAI.",
 "desktopFocused": "The existing desktop input window has been restored.",
 "title": "Live2D Desktop Pet",
 "intro": "Bring your conversations and memories to your desktop companion.",
 "refresh": "Reload settings",
 "viewer": "Native desktop shell",
 "memory": "Conversation mode",
 "conversation": "Desktop conversation",
 "route": "History also appears in web chat.",
 "identity": "Identity & memory",
 "identityHint": "Choose the native web chat context or keep a separate desktop context.",
 "binding": "Independent-context identity (optional)",
 "bindingHint": "Identity only for the independent desktop context; ignored when using web chat. No private conversation is continued.",
 "nickname": "Nickname for the independent context",
 "continueSession": "Use the web chat conversation",
 "continueHint": "Off by default. Web input, desktop input and interactions continue the native web chat context when on. No linked user is required. Off uses an independent context. Switching does not merge or delete conversations.",
 "sharedSession": "Web chat conversation",
 "separateSession": "Separate desktop conversation",
 "sharedDetail": "Web input, desktop input and interactions share the native web chat context.",
 "separateDetail": "Independent desktop adapter and context. Memory plugins follow their own settings.",
 "connection": "Model resources",
 "modelPath": "Current model configuration path",
 "pathHint": "Model JSON, workshop config.json, or LPK. Leave empty to use the loaded model. Match the path and slot to the model currently loaded in 原生壳.",
 "port": "Desktop input port",
 "portHint": "Reopen the input window after changing this",
 "behavior": "Companion behavior",
 "behaviorHint": "Adjust bubbles, voice and click interactions.",
 "bubbleTime": "Bubble duration (seconds)",
 "cooldown": "Click cooldown (seconds)",
 "voice": "Play voice replies",
 "voiceHint": "Play audio generated by KiraAI.",
 "click": "Respond when the model is clicked",
 "clickHint": "Visible parts keep touch input; transparent pixels pass input to the window underneath.",
 "loadModel": "Load selected model",
 "expression": "Expression",
 "motion": "Motion",
 "apply": "Try it",
 "loading": "Loading configuration…",
 "save": "Save & apply",
 "independent": "Separate desktop identity",
 "online": "running",
 "offline": "offline",
 "connected": "Connected",
 "disconnected": "Disconnected",
 "checking": "Waiting for the native shell",
 "linked": "Identity linked",
 "disabled": "Disabled",
 "unavailable": "Memory plugin unavailable",
 "unbound": "Independent identity",
 "scope": "Recall scope",
 "scopeHint": "Choose linked or global to recall across conversations.",
 "unboundHint": "Choose a direct conversation to share an existing identity.",
 "busy": "Reply in progress",
 "ready": "Ready",
 "saved": "Settings saved. The desktop input will reconnect automatically.",
 "clean": "Configuration is up to date",
 "dirty": "Unsaved changes",
 "saving": "Applying configuration…",
 "sent": "Command sent. Check the 原生壳 window.",
 "testDirty": "Save your changes before testing.",
 "neutral": "Default",
 "loadError": "Could not load configuration. Check that the plugin is enabled.",
 "networkError": "Cannot reach KiraAI. Check the connection.",
 "httpError": "Request failed",
 "refreshDone": "Status refreshed",
 "pending": "Please wait…",
 "discard": "Reload settings and discard unsaved changes?"
};
let activeModelKey=null,modelConflict=false,actionEpoch=0;
const mappingRenderKeys=new Map();
let inlineDrafts={};
let opening=false,reloading=false,online=false,refreshTask=null,noticeTimer=null,touchPolling=false;
let lang='zh', revision='', config=null, dirty=false, saving=false, testing=false;
const originals=new Map();
const foldStorageKey='kira-live2d-settings-folds-v1';
function setupFolds(){
 let saved={};try{const value=JSON.parse(localStorage.getItem(foldStorageKey)||'{}');if(value&&typeof value==='object'&&!Array.isArray(value))saved=value;}catch{}
 const folds=[...document.querySelectorAll('details[data-fold-key]')];
 const remember=()=>{try{localStorage.setItem(foldStorageKey,JSON.stringify(Object.fromEntries(folds.map(fold=>[fold.dataset.foldKey,fold.open]))));}catch{}};
 for(const fold of folds){
  if(typeof saved[fold.dataset.foldKey]==='boolean')fold.open=saved[fold.dataset.foldKey];
  fold.addEventListener('toggle',remember);
 }
 $('expand-folds').addEventListener('click',()=>{folds.forEach(fold=>fold.open=true);remember();});
 $('collapse-folds').addEventListener('click',()=>{folds.forEach(fold=>fold.open=false);remember();});
 $('settings').addEventListener('invalid',event=>{
  for(let parent=event.target.parentElement;parent;parent=parent.parentElement)if(parent.matches('details[data-fold-key]'))parent.open=true;
 },true);
}
setupFolds();
function t(key, fallback=key){return lang==='en'?(english[key]||fallback):fallback;}
function translate(ctx){
 lang=String(ctx?.locale||'zh').startsWith('en')?'en':'zh';
 document.documentElement.lang=lang==='en'?'en':'zh-CN';
 document.querySelectorAll('[data-i18n]').forEach(el=>{if(!originals.has(el)) originals.set(el,el.textContent);el.textContent=t(el.dataset.i18n,originals.get(el));});
 if(config){renderOptions(lastData);renderStatus(lastData.status);updateSave();}
}
function notify(text,error=false){clearTimeout(noticeTimer);$('notice').hidden=false;$('notice').className=error?'error':'success';$('notice-text').textContent=text;if(!error)noticeTimer=setTimeout(()=>$('notice').hidden=true,4500);}
$('dismiss-notice').addEventListener('click',()=>{clearTimeout(noticeTimer);$('notice').hidden=true;});
async function api(path,body){
 const token=window.PluginPageContext?.getToken?.(),controller=new AbortController(),timer=setTimeout(()=>controller.abort(),path==='model/unpack'?300000:path==='model/prepare'?120000:['model/select','native/mode','settings'].includes(path)?30000:12000);
 try{
  const response=await fetch('/api/plugin/kira-ai-plugin-live2d/'+path,{method:body===undefined?'GET':'POST',credentials:'same-origin',cache:'no-store',signal:controller.signal,headers:{'Content-Type':'application/json',...(token?{Authorization:'Bearer '+token}:{})},...(body===undefined?{}:{body:JSON.stringify(body)})});
  const data=await response.json().catch(error=>{if(error.name==='AbortError')throw error;return {};});if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:t('httpError','请求失败')+' ('+response.status+')');return data;
 }catch(error){if(error.name==='AbortError')throw Error(t('timeout','请求超时，请稍后重试。'));if(error instanceof TypeError)throw Error(t('networkError','无法连接 KiraAI，请检查连接。'));throw error;}
 finally{clearTimeout(timer);}
}
let lastData=null;
function setOptions(el,items,value){if(!items.some(item=>item.value===value))value=items[0]?.value||'';el.replaceChildren(...items.map(item=>{const option=document.createElement('option');option.value=item.value;option.textContent=item.label;return option;}));el.value=value;}
function renderOptions(data){renderModel(data);renderLibrary(data.model_library||[]);renderModelTools(data.model_tools||{});}
function renderLibrary(items, selected=$('native_model_path').value){
 const entries=[...items];
 if(selected&&!entries.some(item=>item.path===selected))entries.unshift({path:selected,name:selected.split(/[\\/]/).pop().replace(/\.model3\.json$/i,''),available:true});
 const counts=new Map();for(const item of entries)counts.set(item.name,(counts.get(item.name)||0)+1);
 setOptions($('model-library'),[{value:'',label:'请选择模型',disabled:true},...entries.map((item,index)=>({value:item.path,label:item.name+(counts.get(item.name)>1?' · '+(index+1):'')+(item.available?'':'（文件已不可用）'),disabled:!item.available}))],selected);
 for(const option of $('model-library').options)option.disabled=!option.value||entries.find(item=>item.path===option.value)?.available===false;
}
$('model-library').addEventListener('change',()=>switchModel($('model-library').value));
async function switchModel(selected){
 if(!config||saving||reloading||testing||importingModel)return;
 const values=readForm();
 if(Object.keys(values).some(key=>key!=='native_model_path'&&JSON.stringify(values[key])!==JSON.stringify(config[key]))){notify('请先保存当前修改，或重新读取后再切换模型。',true);$('model-library').value=$('native_model_path').value;return;}
 if(selected===config.native_model_path){$('native_model_path').value=selected;dirty=false;updateSave();return;}
 saving=true;actionEpoch++;updateSave();notify(config.shell_connection_mode==='disabled'?'正在切换模型…':'正在切换模型并重新加载壳…');
 try{const result=await api('model/select',{path:selected,revision});applyData(result,true);if(!result.status.viewer_connected&&config.shell_connection_mode==='local')beginShellSync();else notify('模型已切换，资源和状态已更新。');}
 catch(error){renderLibrary(lastData.model_library||[],$('native_model_path').value);notify(error.message,true);}
 finally{saving=false;updateSave();}
}
function endShellSync(){if(shellSyncTimer)clearInterval(shellSyncTimer);shellSyncTimer=null;shellExpectedKey=null;}
function beginShellSync(){
 endShellSync();if(config?.shell_connection_mode!=='local')return;shellExpectedKey=activeModelKey;shellSyncDeadline=Date.now()+120000;
 if(lastData?.status){lastData.status.viewer_connected=false;lastData.status.viewer_error='正在启动模型，加载后自动更新资源和状态…';renderStatus(lastData.status);}
 shellSyncTimer=setInterval(()=>{
  if(activeModelKey!==shellExpectedKey){endShellSync();return;}
  if(Date.now()>shellSyncDeadline){endShellSync();notify(lastData?.status?.viewer_error||'模型启动尚未完成，请检查连接状态。',true);return;}
  refresh();
 },1000);
}
function renderModelTools(data){
 const unpack=data.import_state||{},copy=data.copy||{};
 $('lpk-tool-status').textContent=(data.unpacker_ready?'解包工具已就绪。':'首次解包时自动下载工具。')+(unpack.message?' '+unpack.message:'');
 $('ai-copy-status').textContent=copy.message||'保存后，模型启动时按开关设置自动生成并应用控制副本。';
}
$('choose-model-package').addEventListener('click',()=>$('model-package-files').click());
$('choose-model-folder').addEventListener('click',()=>$('model-folder-files').click());
for(const id of ['model-folder-files','model-package-files'])$(id).addEventListener('change',async()=>{const files=[...$(id).files];$(id).value='';await importModels(files);});
async function collectModelEntry(entry,prefix=''){
 if(entry.isFile)return [await new Promise((resolve,reject)=>entry.file(file=>resolve({file,path:prefix+file.name}),reject))];
 if(!entry.isDirectory)return [];
 const reader=entry.createReader(),result=[];
 while(true){const batch=await new Promise((resolve,reject)=>reader.readEntries(resolve,reject));if(!batch.length)break;for(const child of batch)result.push(...await collectModelEntry(child,prefix+entry.name+'/'));}
 return result;
}
const drop=$('model-drop');
for(const name of ['dragenter','dragover'])drop.addEventListener(name,event=>{event.preventDefault();if(!importingModel)drop.classList.add('is-dragover');});
drop.addEventListener('dragleave',event=>{if(!drop.contains(event.relatedTarget))drop.classList.remove('is-dragover');});
drop.addEventListener('drop',async event=>{
 event.preventDefault();drop.classList.remove('is-dragover');
 if(importingModel||!config||saving||reloading||testing)return;
 try{const entries=[...event.dataTransfer.items].filter(item=>item.kind==='file').map(item=>item.webkitGetAsEntry?.()).filter(Boolean);
 const files=entries.length?(await Promise.all(entries.map(entry=>collectModelEntry(entry)))).flat():[...event.dataTransfer.files];await importModels(files);
 }catch(error){notify('无法读取拖入的模型：'+error.message,true);}
});
async function importModels(files){
 if(!files.length||importingModel||!config||saving||reloading||testing)return;
 if(dirty){notify('请先保存当前修改，或重新读取后再导入模型。',true);return;}
 const entries=files.map(item=>item.file?item:{file:item,path:item.webkitRelativePath||item.name});
 if(entries.length>4096||entries.reduce((sum,item)=>sum+item.file.size,0)>512*1024*1024){notify('模型最多 4096 个文件、512 MB。',true);return;}
 const body=new FormData();for(const item of entries)body.append('files',item.file,item.file.name);body.append('paths',JSON.stringify(entries.map(item=>item.path)));
 let autoSelectPath=null;
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),600000);
 importingModel=true;actionEpoch++;$('model-import-status').textContent='正在上传并检查模型资源；LPK 首次使用会下载工具并自动解包…';updateSave();
 let progressBusy=false;const progressTimer=setInterval(async()=>{if(progressBusy||!importingModel)return;progressBusy=true;try{const state=await api('model/tools');if(importingModel){renderModelTools(state);if(state.import_state?.message)$('model-import-status').textContent=state.import_state.message;}}catch{}finally{progressBusy=false;}},1000);
 try{const token=window.PluginPageContext?.getToken?.();const response=await fetch('/api/plugin/kira-ai-plugin-live2d/model/import',{method:'POST',body,credentials:'same-origin',headers:token?{Authorization:'Bearer '+token}:{},signal:controller.signal});
 const data=await response.json();if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'模型上传失败');
 lastData.model_library=data.model_library;if(data.model_tools){lastData.model_tools=data.model_tools;renderModelTools(data.model_tools);}
 const selected=data.imported.length===1?data.imported[0]:config.native_model_path;
 $('native_model_path').value=selected;renderLibrary(data.model_library,selected);dirty=JSON.stringify(readForm())!==JSON.stringify(config);
 $('model-import-status').textContent='已导入 '+data.imported.length+' 个模型。'+(data.imported.length===1?(dirty?'正在自动应用模型…':'当前模型已在使用，无需切换。'):'从下方选择模型后自动应用。');
 if(data.imported.length===1&&dirty)autoSelectPath=selected;
 else notify('模型已加入列表，可从下方选择使用。');
 }catch(error){$('model-import-status').textContent='导入失败，当前模型未更改。';notify(error.name==='AbortError'?'上传超时，请重试。':error.message,true);}
 finally{clearTimeout(timer);clearInterval(progressTimer);importingModel=false;updateSave();}
 if(autoSelectPath)await switchModel(autoSelectPath);
}
function status(id,label,good){$(id).textContent=label;$(id).className=good?'good':'warn';}
function renderStatus(s){
 const native=true;
 if(shellExpectedKey!==null&&activeModelKey===shellExpectedKey&&s.viewer_connected){endShellSync();notify('模型已加载，资源和状态已自动更新。');}
 const mode=config?.shell_connection_mode||'disabled';
 status('viewer-status',mode==='disabled'?'未启动':t(s.viewer_connected?'connected':'disconnected',s.viewer_connected?'已连接':mode==='remote'?'等待远程设备连接':'未连接'),mode!=='disabled'&&s.viewer_connected);
 $('viewer-detail').textContent=mode==='disabled'?'选择连接模式后立即启动并保存选择':s.viewer_connected?(mode==='remote'?'远程设备 · 原生渲染':'本机桌宠 · 原生 OpenGL'):(s.viewer_error||t('checking','正在准备模型'));
 const shared=Boolean(config?.continue_bound_session);
 status('memory-status',shared?t('sharedSession','网页聊天会话'):t('separateSession','桌宠独立会话'),true);
 $('memory-detail').textContent=shared?t('sharedDetail','网页、桌面输入和桌宠互动接续网页聊天上下文。'):t('separateDetail','独立适配器与独立上下文，记忆插件按其自身设置处理。');
 const chat=s.pending?'busy':'ready';
 status('chat-status',t(chat,{busy:'正在回复',ready:'已就绪'}[chat]),chat==='ready');
}
function previewTargetChanged(){
 if(!config)return true;
 const draft=readForm();return ['native_model_path'].some(key=>draft[key]!==config[key]);
}
function updateSave(){
 const bridgeBusy=['downloading','installing'].includes(lastData?.event_bridge?.stage);
 const autoBusy=Boolean(lastData?.auto_model?.busy);
 const previewBusy=Boolean(lastData?.drag_preview?.busy);
 const layoutBusy=Boolean(lastData?.layout?.busy);
 const busy=importingModel||saving||opening||reloading||testing||Boolean(lastData?.expression_preview?.active)||bridgeBusy||autoBusy||previewBusy||layoutBusy||Boolean(lastData?.outfit_busy);
 if($('cancel-screen'))$('cancel-screen').disabled=!config||!online||busy||modelConflict||!lastData?.screen_status?.scheduled;
 for(const id of ['choose-model-folder','choose-model-package','model-library'])$(id).disabled=!config||!online||busy||modelConflict;
 $('rescan-model').disabled=!config||!online||busy||modelConflict||previewTargetChanged()||!lastData?.status?.viewer_connected||!lastData?.model_tracking?.following||lastData?.status?.pending;
 document.querySelectorAll('[data-map-reset],[data-map-remove]').forEach(button=>button.disabled=!config||!online||busy||modelConflict);
 document.querySelectorAll('[data-map-select]').forEach(button=>{const section=button.dataset.mapSelect;button.disabled=!config||!online||busy||modelConflict||!resourcePolicy()[section+'_enabled']||!$('resolved-'+section).children.length||!$('resolved-'+section).querySelector('[data-map-name]');});
 $('restore-layout').disabled=!config||!online||busy||dirty||modelConflict||!lastData?.layout?.can_restore||!lastData?.status?.viewer_connected||lastData?.status?.pending;
 $('open-desktop').disabled=!config||!online||busy||config.shell_connection_mode==='disabled';
 $('shell_connection_mode').disabled=!config||!online||busy||modelConflict||Boolean(lastData?.status?.pending);
 $('open-desktop').textContent=opening?t('openingDesktop','正在打开…'):t('openDesktop','打开桌面输入窗口');
 $('open-desktop').classList.toggle('is-loading',opening);
 $('open-desktop').setAttribute('aria-busy',String(opening));
 $('refresh').disabled=busy;
 $('refresh').textContent=reloading?t('refreshing','正在刷新…'):t('refresh','重新读取');
 $('refresh').classList.toggle('is-loading',reloading);
 $('refresh').setAttribute('aria-busy',String(reloading));
 $('dismiss-notice').setAttribute('aria-label',t('dismiss','关闭提示'));
 $('save').disabled=!config||busy||!dirty||modelConflict;
 $('save-state').textContent=saving?t('saving','正在应用配置…'):dirty?t('dirty','有尚未保存的更改'):t('clean','配置已同步');
 $('fields').disabled=!config||saving||reloading||bridgeBusy||autoBusy||previewBusy||layoutBusy||Boolean(lastData?.outfit_busy);
 refreshInlineButtons();
 document.querySelectorAll('[data-expression-preview],[data-motion-preview],[data-drag-preview]').forEach(el=>{const mapping=el.hasAttribute('data-expression-preview')||el.hasAttribute('data-motion-preview');const savedAvailable=el.hasAttribute('data-expression-preview')?lastData?.expressions?.includes(el.dataset.expressionPreview):el.hasAttribute('data-motion-preview')?lastData?.motions?.includes(el.dataset.motionPreview):true;el.disabled=el.dataset.unavailable==='true'||!savedAvailable||!config||!online||busy||(mapping?previewTargetChanged():dirty)||modelConflict||!lastData?.status?.viewer_connected;el.title=mapping?t('previewAppliedModel','预览当前已应用模型的资源；修改连接或模型后需先保存，新启用的资源也需先保存。'):'';});
 document.querySelectorAll('[data-expression-preview]').forEach(button=>{const active=lastData?.expression_preview?.active&&lastData.expression_preview.name===button.dataset.expressionPreview;button.textContent=active?t('endExpressionPreview','结束预览'):t('expressionPreviewButton','预览（3秒）');button.setAttribute('aria-label',button.textContent+' '+button.dataset.expressionPreview);if(active)button.disabled=testing;});
 document.querySelectorAll('[data-motion-preview]').forEach(button=>{button.textContent=t('motionPreviewButton','预览');button.setAttribute('aria-label',button.textContent+' '+button.dataset.motionPreview);});
 document.querySelectorAll('[data-outfit-preview]').forEach(button=>{
  const row=button.closest('.outfit-entry'),expression=row.querySelector('[data-outfit-resource="expression"]').value,motion=row.querySelector('[data-outfit-resource="motion"]').value,policy=resourcePolicy();
  const expressionOk=!expression||(policy.expressions_enabled&&!policy.disabled_expressions.includes(expression)&&(expression==='默认'?lastData?.expression_default_enabled!==false:lastData?.expressions?.includes(expression)));
  const motionOk=!motion||(policy.motions_enabled&&!policy.disabled_motions.includes(motion)&&lastData?.motions?.includes(motion));
  button.disabled=!config||!online||busy||modelConflict||!lastData?.status?.viewer_connected||lastData?.status?.pending||lastData?.model_tracking?.following===false||!(expression||motion)||!expressionOk||!motionOk;
 });
 nativeControls(busy);
}
function nativeControls(busy){
 for(const id of ['viewer_url','model_index','renderer_mode','auto_ai_control'])if($(id))$(id).disabled=true;
 const native=true;
 if($('action_agent_enabled'))$('action_agent_enabled').disabled=!native||$('fields').disabled;
 if($('action-agent-status'))$('action-agent-status').textContent=native?((lastData?.action_agent?.label?lastData.action_agent.label+' · ':'')+(lastData?.action_agent?.message||'等待动作 Agent')+(lastData?.action_agent?.next_check?' · 下次复查：'+new Date(lastData.action_agent.next_check*1000).toLocaleTimeString():'')):'独立动作 Agent 仅在独立壳模式生效';
 const restart=$('native-restart');if(restart){restart.hidden=!native;restart.disabled=!native||!online||busy||dirty||modelConflict||config?.shell_connection_mode==='disabled';}
 const debug=$('native-debug');if(debug)debug.disabled=!online||busy||dirty||modelConflict||!lastData?.status?.viewer_connected;
}
$('native-debug')?.addEventListener('click',async()=>{
 if($('native-debug').disabled)return;testing=true;updateSave();
 try{const result=await api('native/debug',{revision});notify(result.message);}catch(error){notify(error.message,true);}finally{testing=false;updateSave();}
});
$('native-restart')?.addEventListener('click',async()=>{
 if($('native-restart').disabled)return;testing=true;actionEpoch++;updateSave();
 try{const result=await api('native/restart',{revision});beginShellSync();notify(result.message);}
 catch(error){notify(error.message,true);}finally{testing=false;updateSave();}
});
$('shell_connection_mode').addEventListener('change',async()=>{
 const select=$('shell_connection_mode'),mode=select.value;
 if(!config||select.disabled)return;
 if(dirty){select.value=config.shell_connection_mode;notify('请先保存当前修改，或重新读取后再切换连接模式。',true);return;}
 saving=true;actionEpoch++;endShellSync();updateSave();notify('正在切换连接模式…');
 try{
  const result=await api('native/mode',{mode,revision});applyData(result,true);
  if(mode==='local'&&result.model_tracking?.following&&!result.status.viewer_connected)beginShellSync();
  notify(mode==='disabled'?'已停止桌宠，连接模式已保存。':mode==='remote'?'远程壳模式已保存，请在远程设备填写连接地址和密钥。':'本机桌宠模式已保存，正在准备模型。');
 }catch(error){select.value=config.shell_connection_mode;notify(error.message,true);}
 finally{saving=false;updateSave();}
});
function readForm(){const values={...config};for(const key of Object.keys(config)){const el=$(key);if(!el)continue;if(el.type==='checkbox')values[key]=el.checked;else if(el.type==='number')values[key]=el.valueAsNumber;else values[key]=el.value.trim();}return values;}
function applyData(data,replace=false){
 const key=data.model_tracking?.key??null;
 if(config&&key!==activeModelKey){
  if(dirty&&!replace){modelConflict=true;notify(t('modelFollowChanged','模型已切换，当前草稿仍属于旧模型。请重新读取后保存，草稿不会应用到新模型。'),true);updateSave();return;}
  replace=true;
 }
 lastData=data;
 if(replace){activeModelKey=key;modelConflict=false;config=data.config;revision=data.revision;renderOptions(data,config.binding_session);for(const [key,value] of Object.entries(config)){const el=$(key);if(!el)continue;if(el.type==='checkbox')el.checked=value;else el.value=value;}renderMappings();renderDragMappings();renderOutfits();dirty=false;}
 const remote=data.remote_shell;
 $('remote-connection').hidden=!remote?.enabled;
 $('remote-address-help').textContent='在远程设备填写运行 KiraAI 电脑的 IP 地址，格式为 http://电脑IP:'+(remote?.port||config?.bridge_port||18765)+'，并填入下面的密钥。两台设备需网络互通。';
 $('remote-access-key').value=remote?.access_key||'';
 $('remote-status').textContent=remote?.connected?'远程壳已连接':'等待远程设备连接。';
 renderOptions(data);renderStatus(data.status);renderScreen(data.screen_status);updateSave();
}
async function loadSettings(manual){
 const epoch=actionEpoch;
 try{const data=await api('settings');if(epoch!==actionEpoch)return;online=true;applyData(data,manual||!config||(!dirty&&(revision!==data.revision||activeModelKey!==(data.model_tracking?.key??null))));if(manual)notify(t('refreshDone','配置已重新读取'));}
 catch(error){if(epoch!==actionEpoch)return;online=false;if(manual||!config)notify(error.message,true);else status('viewer-status',t('networkError','无法连接 KiraAI'),false);updateSave();}
}
async function refresh(manual=false){
 if(manual){
  if(importingModel||reloading||saving||opening||testing)return;
  reloading=true;updateSave();
  try{if(refreshTask)await refreshTask;refreshTask=loadSettings(true);await refreshTask;}
  finally{refreshTask=null;reloading=false;updateSave();}
 }else{
  if(importingModel||refreshTask||reloading||saving||opening||testing||document.hidden)return;
  const task=loadSettings(false);refreshTask=task;
  try{await task;}finally{if(refreshTask===task)refreshTask=null;}
 }
}
$('settings').addEventListener('input',()=>{if(!config)return;dirty=JSON.stringify(readForm())!==JSON.stringify(config);updateSave();});
$('settings').addEventListener('submit',async event=>{
 event.preventDefault();if(importingModel||modelConflict||!validateMappings()||!validateOutfits()||saving||opening||reloading||testing||!config||!dirty)return;saving=true;updateSave();
 try{const result=await api('settings',{config:readForm(),revision});applyData(result,true);if(!result.status.viewer_connected&&config.shell_connection_mode==='local')beginShellSync();notify(t('saved','配置已保存并生效。'));}
 catch(error){notify(error.message,true);}
 finally{saving=false;updateSave();}
});
async function action(kind,name){
 const activeExpression=lastData?.expression_preview;
 if(kind==='expression'&&activeExpression?.active&&activeExpression.name===name){
  if(testing)return;actionEpoch++;testing=true;updateSave();
  try{await api('action',{kind:'expression_preview_stop',nonce:activeExpression.nonce});lastData.expression_preview=null;notify(t('expressionPreviewEnded','表情预览已结束。'));}
  catch(error){notify(error.message,true);}
  finally{testing=false;updateSave();}return;
 }
 if(modelConflict){notify(t('modelFollowChanged','模型已切换，请重新读取配置。'),true);return;}
 if(dirty&&(!['expression','motion'].includes(kind)||previewTargetChanged())){notify(t('testDirty','请先保存更改，再进行测试。'),true);return;}
 if(testing||opening||saving||reloading||!online||activeExpression?.active)return;
 actionEpoch++;testing=true;updateSave();
 try{
  const result=await api('action',{kind,revision,...(['expression','motion'].includes(kind)?{preview:true}:{}),...(name?{name}:{})});
  if(kind==='expression'){lastData.expression_preview=result.expression_preview||null;notify(t('expressionPreviewRunning','表情预览保留 3 秒，之后恢复预览前已知的表情，未知时恢复默认。'));}
  else notify(t('sent','指令已发送，请查看 原生壳 窗口中的效果。'));
 }
 catch(error){notify(error.message,true);}
 finally{testing=false;updateSave();}
}
$('rescan-model').addEventListener('click',async()=>{
 if($('rescan-model').disabled)return;
 const draft=readForm(),hadDraft=dirty,inlineCopy=structuredClone(inlineDrafts);
 actionEpoch++;testing=true;updateSave();
 try{
  const result=await api('model/rescan',{revision});
  applyData(result.settings,true);
  if(!result.settings.status.viewer_connected)beginShellSync();
  if(hadDraft){
   for(const [key,value] of Object.entries(draft)){const el=$(key);if(!el)continue;if(el.type==='checkbox')el.checked=value;else el.value=value;}
   renderMappings();inlineDrafts=inlineCopy;renderDragMappings();renderOutfits();renderOptions(lastData);
   dirty=JSON.stringify(readForm())!==JSON.stringify(config);
  }
  notify(result.warning||t('rescanDone','模型资源已重新识别，已保存配置和未保存修改均已保留。'),Boolean(result.warning));
 }catch(error){notify(error.message,true);}
 finally{testing=false;updateSave();}
});
function renderScreen(state){
 const text=state?.scheduled?t('nextScreen','下次看屏幕：')+new Date(state.due*1000).toLocaleString()+(state.focus?' · '+state.focus:''):t('noScreenSchedule','当前没有看屏幕预约');
 if($('screen-status'))$('screen-status').textContent=text+(state?.message?'\n'+state.message:'');
}
$('cancel-screen')?.addEventListener('click',async()=>{
 if($('cancel-screen').disabled)return;
 testing=true;updateSave();
 try{const result=await api('screen/cancel',{revision});lastData.screen_status=result.screen_status;renderScreen(result.screen_status);}
 catch(error){notify(error.message,true);}
 finally{testing=false;updateSave();}
});
$('open-desktop').addEventListener('click',async()=>{
 if(opening||saving||reloading||testing||!config||!online)return;opening=true;updateSave();
 try{const result=await api('desktop/open',{});notify(result.state==='focused'?t('desktopFocused','已唤出桌面输入窗口。'):result.state==='starting'?t('desktopStarting','桌面输入窗口正在启动，请稍候。'):t('desktopOpened','已请求打开桌面输入窗口，请查看运行 KiraAI 的电脑。'));}
 catch(error){notify(error.message,true);}
 finally{opening=false;updateSave();}
});
$('refresh').addEventListener('click',()=>{if(!dirty||window.confirm(t('discard','重新读取会丢弃尚未保存的更改，是否继续？')))refresh(true);});
window.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue='';}});
const mappingIds={touch:'touch-mappings'};
const regionEnglish={head:'Head',face:'Face',body:'Body',hand:'Hand',arm:'Arm',leg:'Leg',foot:'Foot',hair:'Hair',ear:'Ear',tail:'Tail',chest:'Upper body',belly:'Belly',back:'Back',unknown:'Unassigned (ordinary click)'};
function renderModel(data){
 if(!data.model)return;
 const model=data.model;
 const tracking=data.model_tracking;
 $('model-follow-status').hidden=Boolean(tracking?.following);
 $('model-follow-status').textContent=tracking?(tracking.message+(tracking.name?' · '+tracking.name:'')):t('modelFollowWaiting','等待 原生壳 同步模型');
 const normalModel=['Cubism 2','Cubism 3','原生壳'].includes(model.format);
 const visible=data.manual_mapping||{expressions:!normalModel,motions:!normalModel,touch:!normalModel};
 for(const section of ['expressions','motions'])if(data.model_tracking?.following)visible[section]=true;
 for(const section of ['expressions','motions','touch']){
  $('manual-'+section).hidden=!visible[section];
  $('manual-'+section).querySelectorAll('input,select').forEach(input=>input.disabled=!visible[section]||input.dataset.mapLocked==='true');
 }
 $('mapping-hint').hidden=!Object.values(visible).some(Boolean);
 renderResolvedMappings(data.resolved_mapping||{});
 refreshOutfitOptions();
 $('model-summary').textContent=model.format+' · '+t('modelCounts','表情 / 动作 / 点击区域')+'：'+data.expressions.length+' / '+data.motions.length+' / '+model.hit_areas.length;
 $('model-warnings').hidden=!model.warnings.length;
 $('model-warnings-title').textContent=t('resourceWarnings','资源提示')+'（'+model.warnings.length+'）';
 $('model-warnings-text').textContent=model.warnings.join('\n');
 appendDetectedTouches();
 const areas=(data.touch_candidates||[]).map(item=>item.name+(item.sources?.includes('observed')?t('observedArea','（已收到点击）'):item.sources?.includes('declared')?'':t('inferredArea','（动作组推断）')));
 $('touch-detected').textContent=areas.length?t('detectedCandidates','检测到的点击候选区域')+'：'+areas.join('、'):t('noAreas','暂未识别到点击区域，可在测试模式下点击角色补充。');
 $('touch-mode-status').textContent=config?.touch_test_mode?t('allTestActive','测试模式已开启：触摸、拖动和手动换装只做记录，不触发 AI。'):t('allTestInactive','普通模式：触摸按开关回应，拖动按你填写的事件描述回应。');
 renderTouch(data.last_touch);
 $('layout-status').textContent=data.layout?.message||t(config?.ai_layout_enabled?'layoutEnabled':'layoutDisabled',config?.ai_layout_enabled?'AI 大小与位置控制已开启':'AI 大小与位置控制已关闭');
 if($('drag-preview-status'))$('drag-preview-status').textContent=data.drag_preview?.message||'';
 $('drag-card').hidden=!data.drag_candidates?.length;
 $('event-bridge-status').textContent=data.event_bridge?.message||'';
 renderInteractionEvents(data.interaction_events||[]);
}
const dragPhases={begin:['dragBegin','开始互动'],end:['dragEnd','松手结束'],min:['dragMin','到达最小值'],max:['dragMax','到达最大值']};
function renderDragMappings(){
 let values={};try{values=JSON.parse($('drag_events').value||'{}');}catch{}
 $('drag-mappings').replaceChildren();
 for(const item of lastData?.drag_candidates||[]){
  const card=document.createElement('div');card.className='drag-source';card.dataset.source=item.id;
  const heading=document.createElement('p');heading.className='tip';heading.textContent=(item.name?item.name+' · ':'')+item.area+' → '+item.parameter+(item.enabled?'':'（已禁用）');card.append(heading);
  const preview=document.createElement('button');preview.type='button';preview.className='secondary';preview.dataset.dragPreview=item.id;preview.textContent=t('dragPreview','预览拖动');preview.dataset.unavailable=String(!item.enabled);preview.disabled=!item.enabled;preview.addEventListener('click',()=>previewDrag(item.id));card.append(preview);
  const hint=document.createElement('small');hint.textContent=t('previewHint','观察模型从最小值变化到最大值，再恢复原值。预览不触发 AI。');card.append(hint);
  for(const [phase,[key,cn]] of Object.entries(dragPhases)){
   const label=document.createElement('label');label.textContent=t(key,cn);
   const input=document.createElement('input');input.maxLength=300;input.dataset.phase=phase;input.value=values[item.id]?.[phase]||'';input.placeholder=t('dragDescription','填写要让 AI 感知的事件，留空不触发');input.addEventListener('input',syncDragEvents);label.append(input);card.append(label);
  }
  $('drag-mappings').append(card);
 }
}
async function previewDrag(source){
 if(testing||saving||opening||reloading||dirty||modelConflict||lastData?.drag_preview?.busy)return;
 testing=true;updateSave();
 try{lastData.drag_preview=await api('drag/preview',{revision,source});$('drag-preview-status').textContent=lastData.drag_preview.message;}
 catch(error){notify(error.message,true);}
 finally{testing=false;updateSave();}
}
function syncDragEvents(){
 let previous={};try{previous=JSON.parse($('drag_events').value||'{}');}catch{}
 const visible=new Set((lastData?.drag_candidates||[]).map(item=>item.id));
 const values=Object.fromEntries(Object.entries(previous).filter(([id])=>!visible.has(id)));
 for(const card of $('drag-mappings').children){
  const phases=Object.fromEntries(Array.from(card.querySelectorAll('input')).filter(input=>input.value.trim()).map(input=>[input.dataset.phase,input.value.trim()]));
  if(Object.keys(phases).length)values[card.dataset.source]=phases;
 }
 $('drag_events').value=Object.keys(values).length?JSON.stringify(values):'';
 $('drag_events').dispatchEvent(new Event('input',{bubbles:true}));
}
function renderInteractionEvents(events){
 const fragment=document.createDocumentFragment();
 for(const event of [...events].reverse()){
  const row=document.createElement('p');
  const stage=event.kind==='outfit'?t('outfitInteraction','换装'):event.kind==='touch'?t('touchEvent','触摸'):t(dragPhases[event.phase]?.[0]||'',dragPhases[event.phase]?.[1]||event.phase);
  row.textContent='#'+event.seq+' '+new Date(event.time*1000).toLocaleTimeString()+' · '+stage+' · '+(event.area||'—')+(event.parameter?' / '+event.parameter:'')+'\n'+(event.description||t('emptyDragEvent','未填写事件，不触发 AI'))+(event.test_mode?' · '+t('testModeTitle','测试模式'):'');
  fragment.append(row);
 }
 if(!events.length){const row=document.createElement('p');row.textContent=t('noInteractionEvents','尚未收到触摸或拖动事件。');fragment.append(row);}
 $('interaction-log').replaceChildren(fragment);
}
$('restore-layout').addEventListener('click',async()=>{
 if($('restore-layout').disabled)return;testing=true;updateSave();
 try{const result=await api('layout/restore',{revision});lastData.layout=result.layout;renderModel(lastData);notify(lastData.layout.message);}
 catch(error){notify(error.message,true);}
 finally{testing=false;updateSave();}
});
function outfitOptions(select,kind){
 const selected=select.value;
 const names=kind==='expression'?[...(lastData?.expression_default_enabled!==false?['默认']:[]),...(lastData?.expressions||[])]:(lastData?.motions||[]);
 const items=[{value:'',label:t('outfitNone','不使用')},...[...new Set(names)].map(name=>({value:name,label:name}))];
 if(selected&&!names.includes(selected))items.push({value:selected,label:selected+t('outfitUnavailable','（不可用）')});
 setOptions(select,items,selected);
}
function refreshOutfitOptions(){
 for(const select of document.querySelectorAll('[data-outfit-resource]'))outfitOptions(select,select.dataset.outfitResource);
}
function outfitRow(entry){
 const row=document.createElement('div');row.className='outfit-entry';row.dataset.outfitId=entry.id;
 const field=(text,input)=>{const label=document.createElement('label');label.textContent=text;label.append(input);row.append(label);input.addEventListener('input',syncOutfits);};
 const name=document.createElement('input');name.value=entry.name;name.maxLength=80;name.required=true;name.dataset.outfitName='';field(t('outfitName','换装名称'),name);
 for(const kind of ['expression','motion']){
  const select=document.createElement('select');select.dataset.outfitResource=kind;
  const initial=document.createElement('option');initial.value=entry[kind];initial.textContent=entry[kind];select.append(initial);select.value=entry[kind];outfitOptions(select,kind);
  field(t(kind,kind==='expression'?'表情':'动作'),select);
 }
 const event=document.createElement('input');event.value=entry.event;event.maxLength=300;event.dataset.outfitEvent='';event.placeholder=t('outfitEventHint','例如：你换上了白色连衣裙。留空不触发 AI。');field(t('outfitEvent','告诉 AI 的事件（可留空）'),event);
 const preview=document.createElement('button');preview.type='button';preview.className='secondary';preview.dataset.outfitPreview=entry.id;preview.textContent=t('previewOutfit','预览换装');preview.addEventListener('click',()=>previewOutfit(row));row.append(preview);
 const remove=document.createElement('button');remove.type='button';remove.className='secondary';remove.textContent=t('remove','删除');remove.addEventListener('click',()=>{row.remove();syncOutfits();});row.append(remove);
 $('outfit-mappings').append(row);
}
async function previewOutfit(row){
 if(row.querySelector('[data-outfit-preview]').disabled)return;
 testing=true;updateSave();
 try{await api('outfit/preview',{revision,expression:row.querySelector('[data-outfit-resource="expression"]').value,motion:row.querySelector('[data-outfit-resource="motion"]').value});notify(t('outfitPreviewSent','换装预览请求已发送，不会保存预设或触发 AI。'));}
 catch(error){notify(error.message,true);}
 finally{testing=false;updateSave();}
}
function renderOutfits(){
 let rows=[];try{rows=JSON.parse($('outfits').value||'[]');}catch{}
 $('outfit-mappings').replaceChildren();for(const entry of rows)outfitRow(entry);
}
function syncOutfits(){
 const rows=[...$('outfit-mappings').children].map(row=>{
  const expression=row.querySelector('[data-outfit-resource="expression"]'),motion=row.querySelector('[data-outfit-resource="motion"]');expression.setCustomValidity('');motion.setCustomValidity('');
  return {id:row.dataset.outfitId,name:row.querySelector('[data-outfit-name]').value.trim(),expression:expression.value,motion:motion.value,event:row.querySelector('[data-outfit-event]').value.trim()};
 });
 $('outfits').value=rows.length?JSON.stringify(rows):'';$('outfits').dispatchEvent(new Event('input',{bubbles:true}));
}
function validateOutfits(){
 for(const row of $('outfit-mappings').children){const expression=row.querySelector('[data-outfit-resource="expression"]'),motion=row.querySelector('[data-outfit-resource="motion"]');expression.setCustomValidity(expression.value||motion.value?'':t('outfitResourceRequired','至少选择一个表情或动作'));if(!expression.reportValidity())return false;}return true;
}
$('add-outfit').addEventListener('click',()=>{
 const id=Array.from(crypto.getRandomValues(new Uint8Array(12)),value=>value.toString(16).padStart(2,'0')).join('');
 outfitRow({id,name:'',expression:'',motion:'',event:''});syncOutfits();$('outfit-mappings').lastElementChild.querySelector('input').focus();
});
function resourcePolicy(){
 let value={};try{value=JSON.parse($('resource_policy').value||'{}');}catch{}
 const policy={expressions_enabled:true,motions_enabled:true,disabled_expressions:[],disabled_motions:[],enabled_expressions:[],enabled_motions:[],appearance_expressions:[],appearance_motions:[],...value};
 for(const section of ['expressions','motions'])for(const [name,info] of Object.entries(lastData?.resource_analysis?.[section]||{}))if(info.uncertain&&!info.appearance&&!policy['appearance_'+section].includes(name)&&!policy['enabled_'+section].includes(name)&&!policy['disabled_'+section].includes(name))policy['disabled_'+section].push(name);
 return policy;
}
function writeResourcePolicy(value){
 $('resource_policy').value=JSON.stringify(value);
 $('resource_policy').dispatchEvent(new Event('input',{bubbles:true}));
 renderResolvedMappings(lastData?.resolved_mapping||{});updateSave();
}
for(const section of ['expressions','motions'])$('allow-'+section).addEventListener('input',event=>{
 const policy=resourcePolicy();policy[section+'_enabled']=event.target.checked;writeResourcePolicy(policy);
});
$('allow-default-expression').addEventListener('input',event=>{
 const policy=resourcePolicy();policy.disabled_expressions=policy.disabled_expressions.filter(name=>name!=='默认');
 if(!event.target.checked)policy.disabled_expressions.push('默认');writeResourcePolicy(policy);
});
function mappingEntries(section,mapping){return Object.entries(mapping||{}).map(([name,value])=>({name,value:section==='motions'&&typeof value==='string'?{type:0,mtn:value}:value}));}
function inlineKey(section,rows,policy){return JSON.stringify([lang,activeModelKey,rows,policy[section+'_enabled'],policy['disabled_'+section],policy['appearance_'+section],lastData?.resource_analysis?.[section]]);}
function writeOverrides(data){for(const key of Object.keys(data))if(!Object.keys(data[key]||{}).length)delete data[key];$('model_overrides').value=Object.keys(data).length?JSON.stringify(data):'';$('model_overrides').dispatchEvent(new Event('input',{bubbles:true}));}
function inlineRowValue(row,section){return section==='expressions'?row.querySelector('[data-map-target]').valueAsNumber:{type:Number(row.querySelector('[data-map-type]').value),mtn:row.querySelector('[data-map-target]').value.trim()};}
function syncInline(section){
 for(const row of $('resolved-'+section).querySelectorAll('[data-inline-row]')){
  const name=row.querySelector('[data-map-name]').value.trim(),previous=row.dataset.previousName;
  if(name&&previous&&name!==previous){
   const policy=resourcePolicy();for(const prefix of ['enabled_','disabled_','appearance_'])if(policy[prefix+section].includes(previous))policy[prefix+section]=Array.from(new Set(policy[prefix+section].map(n=>n===previous?name:n)));$('resource_policy').value=JSON.stringify(policy);
   let changed=false;
   for(const select of document.querySelectorAll('[data-outfit-resource="'+(section==='expressions'?'expression':'motion')+'"]'))if(select.value===previous){const option=document.createElement('option');option.value=name;option.textContent=name;select.append(option);select.value=name;changed=true;}
   if(changed)syncOutfits();
  }
  if(name)row.dataset.previousName=name;
 }
 for(const input of $('resolved-'+section).querySelectorAll('input,select'))input.setCustomValidity('');
 const rows=[...$('resolved-'+section).querySelectorAll('[data-inline-row]')].map(row=>({name:row.querySelector('[data-map-name]').value.trim(),value:inlineRowValue(row,section)}));
 inlineDrafts[section]=rows;
 let data={};try{data=JSON.parse($('model_overrides').value||'{}');}catch{}
 data[section]=Object.fromEntries(rows.map(row=>[row.name,row.value]));
 const policy=resourcePolicy();let policyChanged=false;
 for(const row of $('resolved-'+section).querySelectorAll('[data-inline-row]')){
  const name=row.querySelector('[data-map-name]').value.trim();
  if(name&&!row.querySelector('[data-resource-name]').checked&&!policy['disabled_'+section].includes(name)){policy['disabled_'+section].push(name);policyChanged=true;}
 }
 if(policyChanged)$('resource_policy').value=JSON.stringify(policy);
 mappingRenderKeys.set(section,inlineKey(section,rows,policy));
 writeOverrides(data);refreshInlineButtons();updateSave();
}
function refreshInlineButtons(){
 const policy=resourcePolicy();
 for(const row of document.querySelectorAll('[data-inline-row]')){
  const section=row.dataset.inlineRow,name=row.querySelector('[data-map-name]').value.trim(),value=inlineRowValue(row,section),kind=section==='expressions'?'expression':'motion';
  const button=row.querySelector('[data-'+kind+'-preview]');
  button.dataset[kind+'Preview']=name;
  const saved=lastData?.resolved_mapping?.[section]?.[name],same=JSON.stringify(value)===JSON.stringify(saved);
  button.dataset.unavailable=String(!same||!policy[section+'_enabled']||policy['disabled_'+section].includes(name));
  row.querySelector('[data-resource-name]').dataset.resourceName=name;
 }
}
function renderResolvedMappings(mapping){
 const policy=resourcePolicy();
 $('allow-expressions').checked=policy.expressions_enabled;$('allow-motions').checked=policy.motions_enabled;
 $('allow-default-expression').checked=!policy.disabled_expressions.includes('默认');$('allow-default-expression').disabled=!policy.expressions_enabled;
 for(const section of ['expressions','motions']){
  const rows=inlineDrafts[section]??mappingEntries(section,mapping[section]),body=$('resolved-'+section),key=inlineKey(section,rows,policy);
  if(mappingRenderKeys.get(section)===key)continue;
  const fragment=document.createDocumentFragment();
  for(const item of rows){
   const {name,value}=item,row=document.createElement('tr');row.dataset.inlineRow=section;row.dataset.previousName=name;
   const label=document.createElement('td'),nameInput=document.createElement('input');nameInput.value=name;nameInput.required=true;nameInput.maxLength=100;nameInput.dataset.mapName=section;nameInput.setAttribute('aria-label',t('mappingName','名称'));label.append(nameInput);
   const target=document.createElement('td'),input=document.createElement('input');input.dataset.mapTarget=section;input.required=true;
   if(section==='expressions'){input.type='number';input.min=0;input.max=4095;input.step=1;input.value=value;input.setAttribute('aria-label',t('expressionIndex','原生壳 编号'));}
   else{
    const type=document.createElement('input');type.type='hidden';type.dataset.mapType='';type.value=String(value.type);const typeLabel=document.createElement('small');typeLabel.textContent=value.type===1?t('motionFile','动作文件'):t('motionGroup','动作组 / 事件');target.append(typeLabel,type);input.value=value.mtn;input.maxLength=2000;input.setAttribute('aria-label',t('motionTarget','动作组 / 事件 / 文件'));
   }
   input.readOnly=true;target.append(input);
   const hint=lastData?.resource_analysis?.[section]?.[name];
   if(hint){const detail=document.createElement('small');detail.textContent='用途建议：'+hint.summary+(hint.playback_hint?' · '+hint.playback_hint:(hint.duration!=null?' · 片段 '+hint.duration+' 秒':''));detail.title='按名称和参数分析，请预览确认；手填名称保持不变';target.append(detail);}
   nameInput.addEventListener('input',()=>syncInline(section));input.addEventListener('input',()=>syncInline(section));row.append(label,target);
   const kind=section==='expressions'?'expression':'motion',previewCell=document.createElement('td'),preview=document.createElement('button');preview.type='button';preview.className='secondary';preview.dataset[kind+'Preview']=name;preview.textContent=t('preview','预览');preview.addEventListener('click',()=>action(kind,nameInput.value.trim()));previewCell.append(preview);row.append(previewCell);
   const enabledCell=document.createElement('td'),enabled=document.createElement('input');enabled.type='checkbox';enabled.dataset.resourceSection=section;enabled.dataset.resourceName=name;enabled.checked=!policy['disabled_'+section].includes(name);enabled.disabled=!policy[section+'_enabled'];enabled.setAttribute('aria-label',t('resourceAvailable','可用')+' '+name);enabled.addEventListener('input',()=>{const value=resourcePolicy(),current=nameInput.value.trim();value['disabled_'+section]=value['disabled_'+section].filter(n=>n!==current);value['enabled_'+section]=value['enabled_'+section].filter(n=>n!==current);if(current)value[(enabled.checked?'enabled_':'disabled_')+section].push(current);writeResourcePolicy(value);});enabledCell.append(enabled);row.append(enabledCell);
   const actions=document.createElement('td'),remove=document.createElement('button');remove.type='button';remove.className='secondary';remove.textContent=t('remove','删除');remove.dataset.mapRemove='';remove.addEventListener('click',()=>{row.remove();syncInline(section);});actions.append(remove);row.append(actions);fragment.append(row);
  }
  if(!fragment.childNodes.length){const row=document.createElement('tr'),cell=document.createElement('td');cell.colSpan=5;cell.textContent=t('noResolvedMappings','尚未读取到映射。');row.append(cell);fragment.append(row);}
  body.replaceChildren(fragment);mappingRenderKeys.set(section,key);
 }
 refreshInlineButtons();
}
for(const button of document.querySelectorAll('[data-map-select]'))button.addEventListener('click',()=>{
 if(button.disabled)return;
 const section=button.dataset.mapSelect,policy=resourcePolicy();
 const names=new Set(Array.from($('resolved-'+section).querySelectorAll('[data-map-name]'),input=>input.value.trim()).filter(Boolean));
 const key='disabled_'+section;
 policy[key]=policy[key].filter(name=>!names.has(name));
 policy['enabled_'+section]=policy['enabled_'+section].filter(name=>!names.has(name));
 if(button.dataset.selectValue==='none')policy[key]=Array.from(new Set([...policy[key],...names]));
 else policy['enabled_'+section]=Array.from(new Set([...policy['enabled_'+section],...names]));
 writeResourcePolicy(policy);
});
for(const button of document.querySelectorAll('[data-map-reset]'))button.addEventListener('click',event=>{
 event.preventDefault();event.stopPropagation();
 const section=button.dataset.mapReset;let data={};try{data=JSON.parse($('model_overrides').value||'{}');}catch{}
 delete data[section];inlineDrafts[section]=mappingEntries(section,lastData?.automatic_mapping?.[section]||{});writeOverrides(data);renderResolvedMappings(lastData?.resolved_mapping||{});updateSave();
});
function renderTouch(hit){
 $('touch-latest').textContent=hit?t('lastTouch','最近点击')+(hit.sequence?' #'+hit.sequence:'')+'：'+(hit.area||t('noAreaName','未返回区域名'))+' → '+(lang==='en'?(regionEnglish[hit.region]||hit.label):hit.label):t('noTouch','尚未收到点击。请在 原生壳 中点击所选模型。');
}
function mappingRow(section,name='',value='',detected=false){
 const row=document.createElement('div');row.className='mapping-row';
 const key=document.createElement('input');key.value=name;key.maxLength=100;key.placeholder=t('mapName','名称 / 区域名');key.setAttribute('aria-label',key.placeholder);key.required=true;
 if(detected){key.readOnly=true;row.dataset.detected='true';}
 let target;
 if(section==='touch'){
  target=document.createElement('input');target.type='text';target.maxLength=100;
  target.value=value&&value!=='unknown'?(lastData?.touch_regions?.[value]||value):'';
  target.dataset.originalTouchValue=value;target.dataset.originalTouchLabel=target.value;
  target.placeholder=t('touchPosition','手填具体部位，如头部、左手、裙摆；留空为普通点击');
 }else{target=document.createElement('input');target.type=section==='expressions'?'number':'text';target.value=value;target.required=true;if(section==='expressions'){target.min=0;target.max=4095;target.step=1;}else{target.maxLength=200;target.placeholder=t('mapValue','组名或组名:动作名');}}
 target.setAttribute('aria-label',section==='expressions'?'原生壳 index':section==='touch'?'Body region':'原生壳 motion');
 const remove=document.createElement('button');remove.type='button';remove.className='secondary';remove.textContent=detected?t('resetRegion','清除部位'):t('remove','删除');remove.addEventListener('click',()=>{if(detected)target.value='';else row.remove();syncMappings();});
 key.addEventListener('input',syncMappings);target.addEventListener('input',syncMappings);row.append(key,target,remove);$(mappingIds[section]).append(row);
}
function renderMappings(){
 mappingRenderKeys.clear();
 let data={},saved={};try{data=JSON.parse($('model_overrides').value||'{}');saved=JSON.parse(config?.model_overrides||'{}');}catch{}
 inlineDrafts={};
 for(const section of ['expressions','motions'])if(JSON.stringify(data[section]||{})!==JSON.stringify(saved[section]||{}))inlineDrafts[section]=mappingEntries(section,Object.keys(data[section]||{}).length?data[section]:lastData?.automatic_mapping?.[section]);
 for(const [section,id] of Object.entries(mappingIds)){
  $(id).replaceChildren();
  for(const [name,value] of Object.entries(data[section]||{})){
   const detected=section==='touch'&&(lastData?.touch_candidates||[]).some(item=>(item.aliases||[item.name]).some(alias=>touchKey(alias)===touchKey(name)));
   mappingRow(section,name,value,detected);
  }
 }
 appendDetectedTouches();
}
function touchKey(value){const key=String(value).replace(/[\s_-]/g,'').toLowerCase();return key.startsWith('tap')&&key.length>3?key.slice(3):key;}
function appendDetectedTouches(){
 for(const item of lastData?.touch_candidates||[]){
  const keys=new Set((item.aliases||[item.name]).map(touchKey));
  if(!Array.from($(mappingIds.touch).children).some(row=>keys.has(touchKey(row.children[0].value))))mappingRow('touch',item.name,'unknown',true);
 }
}
function syncMappings(){
 let data={};try{data=JSON.parse($('model_overrides').value||'{}');}catch{}
 delete data.touch;
 document.querySelectorAll('.mapping-row input').forEach(input=>input.setCustomValidity(''));
 for(const [section,id] of Object.entries(mappingIds)){
  const pairs=[];for(const row of $(id).children){const [key,target]=row.children;const name=key.value.trim();if(name&&!(section==='touch'&&!target.value.trim())){const value=section==='expressions'?target.valueAsNumber:section==='touch'&&target.value===target.dataset.originalTouchLabel?target.dataset.originalTouchValue:target.value.trim();pairs.push([name,value]);}}
  if(pairs.length)data[section]=Object.fromEntries(pairs);
 }
 $('model_overrides').value=Object.keys(data).length?JSON.stringify(data):'';
 $('model_overrides').dispatchEvent(new Event('input',{bubbles:true}));
}
function validateMappings(){
 for(const section of ['expressions','motions']){const names=new Set();for(const row of $('resolved-'+section).querySelectorAll('[data-inline-row]')){const name=row.querySelector('[data-map-name]');name.setCustomValidity(names.has(name.value.trim())?t('duplicateMap','同组映射名称不能重复'):'');names.add(name.value.trim());for(const input of row.querySelectorAll('input:not([type=checkbox]),select'))if(!input.reportValidity())return false;}}
 for(const [section,id] of Object.entries(mappingIds)){
  if($('manual-'+section).hidden)continue;
  const names=new Set();for(const row of $(id).children){const key=row.children[0];key.setCustomValidity(names.has(key.value.trim())?t('duplicateMap','同组映射名称不能重复'): '');names.add(key.value.trim());if(!key.reportValidity())return false;}
 }
 return true;
}
document.querySelectorAll('.mapping-add[data-section]').forEach(button=>button.addEventListener('click',()=>{mappingRow(button.dataset.section);dirty=true;updateSave();$(mappingIds[button.dataset.section]).lastElementChild.firstElementChild.focus();}));
async function pollTouch(){
 if(touchPolling||modelConflict||document.hidden||saving||reloading)return;
 touchPolling=true;
 try{const data=await api('touch');if(data.model_key!==undefined&&data.model_key!==activeModelKey)return;if(lastData){lastData.last_touch=data.last_touch;lastData.interaction_events=data.interaction_events||[];if(data.event_bridge)lastData.event_bridge=data.event_bridge;if(data.drag_preview)lastData.drag_preview=data.drag_preview;if(data.touch_candidates){lastData.touch_candidates=data.touch_candidates;if(data.touch_candidates.length&&lastData.manual_mapping)lastData.manual_mapping.touch=true;}renderModel(lastData);updateSave();}else renderTouch(data.last_touch);}
 catch{}
 finally{touchPolling=false;}
}
$('copy-remote-key').addEventListener('click',async()=>{
 const field=$('remote-access-key');if(!field.value)return;
 try{
  if(navigator.clipboard?.writeText)await navigator.clipboard.writeText(field.value);
  else{field.focus();field.select();if(!document.execCommand('copy'))throw new Error();}
  notify('访问密钥已复制。');
 }catch{field.focus();field.select();notify('请复制已选中的访问密钥。',true);}
});
$('download-remote-shell').addEventListener('click',async()=>{
 const button=$('download-remote-shell');button.disabled=true;
 try{const token=window.PluginPageContext?.getToken?.();const response=await fetch('/api/plugin/kira-ai-plugin-live2d/remote/download',{credentials:'same-origin',headers:token?{Authorization:'Bearer '+token}:{}});if(!response.ok)throw new Error('下载远程壳失败');const url=URL.createObjectURL(await response.blob());const link=document.createElement('a');link.href=url;link.download='Kira-Live2D-Remote.zip';link.click();setTimeout(()=>URL.revokeObjectURL(url),10000);}
 catch(error){notify(error.message,true);}finally{button.disabled=false;}
});
async function boot(){
 const bridge=window.PluginPageContext;
 if(bridge){bridge.onContext(translate);if(window.parent!==window)translate(await bridge.ready());else translate(bridge.getContext());}
 await refresh(true);setInterval(()=>refresh(),4000);setInterval(pollTouch,1000);
}
boot().catch(error=>notify(error.message,true));
