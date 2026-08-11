
const CONTROL_CONFIG = __CONTROL_CONFIG__;
const state = {
  status:null, command:null, intelligence:null, parameterIntel:null, proposal:null, review:null,
  supervised:null, preflight:null, execution:null, ack:null, arm:null, llmCycle:null, llmStatus:null, autoConsensus:null, responsiveness:null, candles:null, zoneMap:null, zonePlan:null,
  executionEvents:null, epochs:null, outcomes:null, performance:null, riskUnits:null, recoveryAttribution:null, recoveryRisk:null, riskAppetite:null, audit:null, autoApplications:null, accountPerf:null, dirty:{}, symbols:[], selectedSymbol:null, notificationBaseline:null, decisionBaseline:null
};

const viewMeta={
  overview:["Command Center","What Atlas is watching now"],
  market:["Market","Signals, regime, volatility and execution economics"],
  analysis:["Zone Analysis","Daily trade locations and live zone execution"],
  positions:["Portfolio","Exposure and position management"],
  performance:["Performance","Strategic outcomes, execution quality and learning readiness"],
  atlas:["Atlas Brain","Adaptation, evidence and model authority"],
  control:["Settings","Execution authority and advanced controls"],
  history:["System & Audit","System integrity, execution history and audit evidence"],
  help:["Help & Guide","How to understand and operate Atlas"]
};

function go(name){
  document.querySelectorAll(".view").forEach(x=>x.classList.remove("active"));
  document.querySelectorAll(".nav button").forEach(x=>x.classList.toggle("active",x.dataset.view===name));
  document.getElementById("view-"+name).classList.add("active");
  document.getElementById("top-title").textContent=viewMeta[name][0];
  document.getElementById("top-subtitle").textContent=viewMeta[name][1];
}
document.querySelectorAll(".nav button").forEach(b=>b.onclick=()=>go(b.dataset.view));
function filterHelp(query){
  const q=String(query||"").trim().toLowerCase();
  let visible=0;
  document.querySelectorAll("#view-help .help-searchable").forEach(section=>{
    const hay=(section.dataset.help||"")+" "+section.textContent;
    const show=!q||hay.toLowerCase().includes(q);
    section.classList.toggle("help-hidden",!show);
    if(show){visible++; if(q)section.open=true;}
  });
  const empty=document.getElementById("help-no-results");
  if(empty)empty.style.display=visible?"none":"block";
}
function clearHelpSearch(){
  const input=document.getElementById("help-search");
  if(input)input.value="";
  filterHelp("");
}
// Live Market & Entry Analysis has one canonical home in Market.
const fmt=(v,d=2)=>Number.isFinite(Number(v))?Number(v).toFixed(d):"—";
const money=v=>Number.isFinite(Number(v))?new Intl.NumberFormat(undefined,{style:"currency",currency:"USD",maximumFractionDigits:2}).format(Number(v)):"—";
const text=(v,f="—")=>(v===null||v===undefined||v==="")?f:String(v);
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const pretty=s=>String(s??"").replaceAll("_"," ").replace(/\b\w/g,m=>m.toUpperCase());
const age=s=>{s=Number(s||0); if(s<60)return Math.round(s)+"s"; if(s<3600)return Math.floor(s/60)+"m"; return Math.floor(s/3600)+"h "+Math.floor((s%3600)/60)+"m";}
const countdownAge=s=>{s=Math.max(0,Math.ceil(Number(s||0)));const h=Math.floor(s/3600),m=Math.floor((s%3600)/60),sec=s%60;return h?`${h}h ${String(m).padStart(2,"0")}m ${String(sec).padStart(2,"0")}s`:`${m}m ${String(sec).padStart(2,"0")}s`;};
function badgeClass(v){v=String(v||"").toUpperCase();if(v.includes("READY")||v.includes("PASS")||v.includes("CONFIRMED")||v.includes("APPLIED")||v.includes("EXECUTED")||v==="LOW"||v==="APPROVED")return"ok";if(v.includes("BLOCK")||v.includes("FAIL")||v.includes("HIGH")||v.includes("MISMATCH")||v.includes("TIMEOUT")||v.includes("REJECT"))return"bad";return"warn"}
function toast(msg,bad=false){const t=document.getElementById("toast");t.textContent=msg;t.className="toast show"+(bad?" bad":"");setTimeout(()=>t.className="toast",4500)}

const NOTIF_DEFAULTS={inApp:true,browser:false,sound:true,volume:.35,minSeverity:"INFO"};
const SEVERITY_RANK={INFO:0,IMPORTANT:1,WARNING:2,CRITICAL:3};
let notificationSettings={...NOTIF_DEFAULTS};
let notificationAudio=null;
function loadNotificationSettings(){try{notificationSettings={...NOTIF_DEFAULTS,...JSON.parse(localStorage.getItem("atlasNotificationSettings")||"{}")}}catch{};syncNotificationSettingsUI();renderNotifications()}
function syncNotificationSettingsUI(){const map={"notif-inapp":"inApp","notif-browser":"browser","notif-sound":"sound","notif-volume":"volume","notif-min-severity":"minSeverity"};for(const [id,k] of Object.entries(map)){const el=document.getElementById(id);if(!el)continue;if(el.type==="checkbox")el.checked=!!notificationSettings[k];else el.value=notificationSettings[k]}}
function saveNotificationSettings(){notificationSettings.inApp=!!document.getElementById("notif-inapp")?.checked;notificationSettings.browser=!!document.getElementById("notif-browser")?.checked;notificationSettings.sound=!!document.getElementById("notif-sound")?.checked;notificationSettings.volume=Number(document.getElementById("notif-volume")?.value??.35);notificationSettings.minSeverity=document.getElementById("notif-min-severity")?.value||"INFO";localStorage.setItem("atlasNotificationSettings",JSON.stringify(notificationSettings));}
async function requestBrowserNotifications(){if(!("Notification" in window)){toast("Browser notifications are not supported here",true);return}const p=await Notification.requestPermission();const el=document.getElementById("notif-browser");if(p==="granted"){notificationSettings.browser=true;if(el)el.checked=true;saveNotificationSettings();syncNotificationSettingsUI();toast("Browser notifications enabled")}else{notificationSettings.browser=false;if(el)el.checked=false;saveNotificationSettings();syncNotificationSettingsUI();toast("Browser notification permission not granted",true)}}
function setBrowserNotifications(on){if(on&&("Notification" in window)&&Notification.permission!=="granted"){requestBrowserNotifications();return}notificationSettings.browser=on;saveNotificationSettings()}
function notificationStoreKey(){return `atlasNotifications:${state.selectedSymbol||"default"}`}
function getNotifications(){try{return JSON.parse(localStorage.getItem(notificationStoreKey())||"[]")}catch{return[]}}
function setNotifications(v){localStorage.setItem(notificationStoreKey(),JSON.stringify(v.slice(0,150)));renderNotifications()}
function toggleNotifications(){const d=document.getElementById("notify-drawer");d.classList.toggle("open");if(d.classList.contains("open"))renderNotifications()}
function markAllNotificationsRead(){setNotifications(getNotifications().map(n=>({...n,read:true})))}
function renderNotifications(){const list=document.getElementById("notify-list"),count=document.getElementById("notify-count");if(!list||!count)return;const ns=getNotifications(),unread=ns.filter(n=>!n.read).length;count.textContent=unread>99?"99+":unread;count.classList.toggle("show",unread>0);list.innerHTML=ns.length?ns.map(n=>`<div class="notify-item ${n.read?"":"unread"}" onclick="readNotification('${esc(n.id)}')"><div class="notify-row"><div class="notify-title"><span class="notify-sev ${esc(n.severity)}">${esc(n.severity)}</span>${esc(n.title)}</div><span class="notify-time">${new Date(n.at).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"})}</span></div><div class="notify-body">${esc(n.body)}</div></div>`).join(""):'<div class="notify-empty">No Atlas notifications yet.</div>'}
function readNotification(id){setNotifications(getNotifications().map(n=>n.id===id?{...n,read:true}:n))}
function armNotificationAudio(){try{notificationAudio=notificationAudio||new (window.AudioContext||window.webkitAudioContext)();if(notificationAudio.state==="suspended")notificationAudio.resume()}catch{}}
document.addEventListener("pointerdown",armNotificationAudio,{once:true});
function playNotificationSound(severity="INFO"){if(!notificationSettings.sound||SEVERITY_RANK[severity]<SEVERITY_RANK[notificationSettings.minSeverity])return;armNotificationAudio();if(!notificationAudio)return;const patterns={INFO:[[660,.07]],IMPORTANT:[[660,.07],[880,.1]],WARNING:[[520,.09],[520,.09]],CRITICAL:[[440,.12],[660,.12],[440,.16]]};let t=notificationAudio.currentTime+.01;for(const [freq,dur] of patterns[severity]||patterns.INFO){const o=notificationAudio.createOscillator(),g=notificationAudio.createGain();o.frequency.value=freq;g.gain.setValueAtTime(0,t);g.gain.linearRampToValueAtTime(.12*notificationSettings.volume,t+.01);g.gain.exponentialRampToValueAtTime(.001,t+dur);o.connect(g);g.connect(notificationAudio.destination);o.start(t);o.stop(t+dur+.02);t+=dur+.055}}
function testNotificationSound(){playNotificationSound("IMPORTANT")}
function pushAtlasNotification(severity,title,body,key){const now=Date.now(),ns=getNotifications();if(ns.some(n=>n.key===key&&now-new Date(n.at).getTime()<300000))return;const n={id:`${now}-${Math.random().toString(16).slice(2)}`,key,severity,title,body,at:new Date(now).toISOString(),read:false};if(notificationSettings.inApp)setNotifications([n,...ns]);playNotificationSound(severity);if(notificationSettings.browser&&("Notification" in window)&&Notification.permission==="granted"&&document.hidden){try{new Notification(`Atlas · ${title}`,{body,icon:"/assets/atlas-app-icon.png",tag:key})}catch{}}}
function notificationSnapshot(){const s=state.status||{},z=state.zonePlan||{},lp=z?.capital_sizing?.loss_protection||{};return{connected:!!s.connected,open:Number(s.strategy_open_positions||s.open_positions||0),lastTicket:Number(s.last_order_ticket||0),lastSuccess:!!s.last_order_success,zoneState:String(s.zone_directive_state||z.execution_lane||""),zoneSide:String(s.zone_side||z.side||"NONE"),zoneSuspended:!!s.zone_scalp_suspended,capitalVeto:!!s.capital_veto_new_risk,lossState:String(lp.state||"INACTIVE"),policyEpoch:Number(s.policy_epoch||0),appliedCommand:Number(s.applied_command_version||0),recoveryChains:Number(s.active_hedge_chains||0)}}
function evaluateNotifications(){const cur=notificationSnapshot(),prev=state.notificationBaseline;state.notificationBaseline=cur;if(!prev)return;if(prev.connected&&!cur.connected)pushAtlasNotification("CRITICAL","Nyao disconnected","Atlas lost the live Nyao bridge.","nyao-disconnected");if(!prev.connected&&cur.connected)pushAtlasNotification("INFO","Nyao connected","Live execution telemetry is available again.","nyao-connected");if(cur.lastSuccess&&cur.lastTicket&&cur.lastTicket!==prev.lastTicket)pushAtlasNotification("IMPORTANT","Trade opened",`${cur.zoneSide!=="NONE"?cur.zoneSide+" · ":""}Ticket ${cur.lastTicket} · ${state.selectedSymbol||"symbol"}.`,`trade-${cur.lastTicket}`);if(cur.open<prev.open)pushAtlasNotification("INFO","Position closed",`${prev.open-cur.open} strategy position${prev.open-cur.open===1?"":"s"} closed on ${state.selectedSymbol||"symbol"}.`,`close-${Date.now()}`);if(cur.zoneState!==prev.zoneState){if(cur.zoneState==="ZONE_AWARE_SCALP")pushAtlasNotification("INFO",`${cur.zoneSide} zone watching`,`Zone-aware scalping is active while the campaign waits for commit gates.`,`zone-watch-${cur.zoneSide}`);else if(cur.zoneState.includes("ZONE_CAMPAIGN"))pushAtlasNotification("IMPORTANT",`${cur.zoneSide} zone committed`,`Atlas granted the zone campaign execution priority.`,`zone-commit-${cur.zoneSide}`);else if(prev.zoneState&&cur.zoneState==="OUTSIDE_PRIORITY_ZONE")pushAtlasNotification("INFO","Priority zone released","Normal scalp authority restored outside the priority zone.","zone-released")}
if(!prev.capitalVeto&&cur.capitalVeto)pushAtlasNotification("WARNING","New risk paused","Atlas capital authority is temporarily blocking fresh risk.","capital-veto");if(prev.lossState!==cur.lossState&&cur.lossState&&cur.lossState!=="INACTIVE")pushAtlasNotification(cur.lossState==="BRAIN_REVIEW_PENDING"?"WARNING":"INFO","Loss review changed",`Brain review state is now ${pretty(cur.lossState)}.`,`loss-${cur.lossState}`);if(cur.recoveryChains>prev.recoveryChains)pushAtlasNotification("WARNING","Recovery chain active",`${cur.recoveryChains} recovery chain${cur.recoveryChains===1?"":"s"} now active.`,`recovery-${cur.recoveryChains}`);if(cur.policyEpoch!==prev.policyEpoch&&cur.policyEpoch>0)pushAtlasNotification("INFO","Policy epoch changed",`Nyao is now reporting policy epoch ${cur.policyEpoch}.`,`epoch-${cur.policyEpoch}`)}

function scopedUrl(url){
  if(!state.selectedSymbol || !url.startsWith("/api/v1/") || url.startsWith("/api/v1/atlas/symbols"))return url;
  const join=url.includes("?")?"&":"?";
  return `${url}${join}symbol=${encodeURIComponent(state.selectedSymbol)}`;
}
async function api(url,opts={}){const r=await fetch(scopedUrl(url),{cache:"no-store",...opts});let data=null;try{data=await r.json()}catch{}if(!r.ok){const detail=data?.detail;throw new Error(typeof detail==="string"?detail:(detail?.code?detail.code+": "+detail.message:`HTTP ${r.status}`))}return data}
function jsonPost(url,body){return api(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)})}


function decisionStoreKey(){return `atlasDecisionTimeline:${state.selectedSymbol||"default"}`}
function getDecisionTimeline(){try{return JSON.parse(localStorage.getItem(decisionStoreKey())||"[]")}catch{return[]}}
function setDecisionTimeline(v){localStorage.setItem(decisionStoreKey(),JSON.stringify(v.slice(0,240)));renderDecisionTimeline()}
function clearDecisionTimeline(){setDecisionTimeline([]);state.decisionBaseline=decisionSnapshot()}
function addDecisionEvent(kind,title,body,action="overview",key=""){
  const now=Date.now(),events=getDecisionTimeline();
  if(key&&events.some(e=>e.key===key&&now-new Date(e.at).getTime()<60000))return;
  setDecisionTimeline([{id:`${now}-${Math.random().toString(16).slice(2)}`,kind,title,body,action,key,at:new Date(now).toISOString()},...events]);
}
function decisionSnapshot(){
  const s=state.status||{},zp=state.zonePlan||{},cap=zp.capital_sizing||{},lp=cap.loss_protection||{},plan=zp.zone_plan||{};
  return {
    connected:!!s.connected,
    buyEligible:!!s.buy_entry_eligible,sellEligible:!!s.sell_entry_eligible,
    buyReason:String(s.buy_block_reason||""),sellReason:String(s.sell_block_reason||""),
    buyScore:Number(s.buy_adjusted_score??s.buy_score??0),sellScore:Number(s.sell_adjusted_score??s.sell_score??0),
    buyThreshold:Number(s.buy_effective_threshold??s.runtime_min_buy_signal_score??0),sellThreshold:Number(s.sell_effective_threshold??s.runtime_min_sell_signal_score??0),
    scalpCost:!!s.scalp_cost_feasible,scalpStructure:String(s.scalp_structure_reason||""),
    zoneState:String(s.zone_directive_state||zp.execution_lane||""),zoneSide:String(s.zone_side||plan.side||"NONE"),zonePlan:String(s.zone_plan_id||plan.plan_id||""),
    zoneConfirm:Number(s.zone_confirmation_score??plan.confirmation?.zone_confirmation?.combined_score??0),zoneConfirmThreshold:Number(s.zone_confirmation_threshold??plan.confirmation?.zone_confirmation?.threshold??0),
    zoneDirectional:Number(s.zone_directional_score??0),zoneDirectionalThreshold:Number(s.zone_minimum_directional_score??0),zoneSpreadOk:s.zone_spread_within_limit!==false,
    capitalVeto:!!s.capital_veto_new_risk,scalpRisk:Number(cap.approved_scalp_risk_amount||0),zoneRisk:Number(cap.approved_zone_risk_amount||0),reserved:Number(cap.portfolio_allocation?.reserved_active_risk_amount||0),available:Number(cap.portfolio_allocation?.remaining_operating_risk_amount||0),
    lossState:String(lp.state||"INACTIVE"),policyEpoch:Number(s.policy_epoch||0),open:Number(s.strategy_open_positions??s.open_positions??0),lastTicket:Number(s.last_order_ticket||0),lastSuccess:!!s.last_order_success,recovery:Number(s.active_hedge_chains||0)
  }
}
function crossedUp(a,b,t){return Number.isFinite(t)&&t>0&&a<t&&b>=t}
function crossedDown(a,b,t){return Number.isFinite(t)&&t>0&&a>=t&&b<t}
function materiallyChanged(a,b){const base=Math.max(Math.abs(a),1);return Math.abs(b-a)/base>=.15}
function evaluateDecisionTimeline(){
  const cur=decisionSnapshot(),prev=state.decisionBaseline;state.decisionBaseline=cur;if(!prev)return;
  if(prev.connected!==cur.connected)addDecisionEvent(cur.connected?"SYSTEM":"CRITICAL",cur.connected?"Nyao connection restored":"Nyao connection lost",cur.connected?"Atlas can evaluate execution authority again.":"Execution decisions are suspended until live Nyao telemetry returns.","overview",`connected-${cur.connected}`);
  if(prev.zoneState!==cur.zoneState||prev.zonePlan!==cur.zonePlan){
    const title=cur.zoneState==="ZONE_AWARE_SCALP"?`${cur.zoneSide} zone entered WATCHING`:cur.zoneState.includes("ZONE_CAMPAIGN")?`${cur.zoneSide} zone committed`:cur.zoneState==="OUTSIDE_PRIORITY_ZONE"?"Priority zone released":`Zone state → ${pretty(cur.zoneState||"NONE")}`;
    const body=cur.zoneState==="ZONE_AWARE_SCALP"?"Aligned scalping remains active while Atlas waits for campaign commit gates.":cur.zoneState.includes("ZONE_CAMPAIGN")?"The zone campaign owns fresh-entry priority; policy activation is deferred to the campaign boundary.":cur.zoneState==="OUTSIDE_PRIORITY_ZONE"?"Normal scalp authority is restored.":`Current zone side ${cur.zoneSide}.`;
    addDecisionEvent(cur.zoneState.includes("ZONE_CAMPAIGN")?"READY":"ZONE",title,body,"analysis",`zone-${cur.zoneState}-${cur.zonePlan}`)
  }
  if(!prev.zoneSpreadOk&&cur.zoneSpreadOk)addDecisionEvent("READY","Zone execution cost became feasible",`Current spread is now inside the adaptive campaign limit for the ${cur.zoneSide} zone.`,"analysis","zone-spread-pass");
  if(prev.zoneSpreadOk&&!cur.zoneSpreadOk&&cur.zoneState&&cur.zoneState!=="OUTSIDE_PRIORITY_ZONE")addDecisionEvent("BLOCK","Zone execution cost became too expensive",`Spread moved outside the adaptive campaign limit; the zone remains context but cannot commit on cost.`,"analysis","zone-spread-block");
  if(crossedUp(prev.zoneConfirm,cur.zoneConfirm,cur.zoneConfirmThreshold))addDecisionEvent("READY","Zone confirmation threshold reached",`${fmt(cur.zoneConfirm,1)} ≥ ${fmt(cur.zoneConfirmThreshold,1)}. Directional and execution gates still remain authoritative.`,"analysis","zone-confirm-pass");
  if(crossedDown(prev.zoneConfirm,cur.zoneConfirm,cur.zoneConfirmThreshold))addDecisionEvent("BLOCK","Zone confirmation fell below threshold",`${fmt(cur.zoneConfirm,1)} < ${fmt(cur.zoneConfirmThreshold,1)}.`,"analysis","zone-confirm-fail");
  if(crossedUp(prev.zoneDirectional,cur.zoneDirectional,cur.zoneDirectionalThreshold))addDecisionEvent("READY","Zone directional evidence qualified",`${fmt(cur.zoneDirectional,2)} ≥ ${fmt(cur.zoneDirectionalThreshold,2)}.`,"analysis","zone-direction-pass");
  if(!prev.scalpCost&&cur.scalpCost)addDecisionEvent("READY","Scalp execution economics recovered","The current scalp structure can absorb transaction cost without excessive geometry expansion.","market","scalp-cost-pass");
  if(prev.scalpCost&&!cur.scalpCost)addDecisionEvent("BLOCK","Scalp execution economics blocked",pretty(cur.scalpStructure||"COST_STRUCTURE_MISMATCH"),"market","scalp-cost-block");
  for(const side of ["buy","sell"]){const S=side.toUpperCase(),pe=prev[`${side}Eligible`],ce=cur[`${side}Eligible`],pr=prev[`${side}Reason`],cr=cur[`${side}Reason`];if(!pe&&ce)addDecisionEvent("READY",`${S} scalp became eligible`,`${S} score ${fmt(cur[`${side}Score`],2)} / ${fmt(cur[`${side}Threshold`],2)} and all current Nyao entry gates passed.`,"market",`${side}-eligible`);else if(pe&&!ce)addDecisionEvent("BLOCK",`${S} scalp eligibility lost`,pretty(cr||"BLOCKED"),"market",`${side}-blocked-${cr}`);else if(pr!==cr&&cr)addDecisionEvent("GATE",`${S} blocker changed`,`${pretty(pr||"NONE")} → ${pretty(cr)}`,"market",`${side}-reason-${cr}`)}
  if(!prev.capitalVeto&&cur.capitalVeto)addDecisionEvent("RISK","Fresh-risk capital veto activated","Atlas has temporarily closed new independent risk authority.","overview","capital-veto-on");
  if(prev.capitalVeto&&!cur.capitalVeto)addDecisionEvent("READY","Fresh-risk capital authority restored",`${money(cur.available)} operating capacity is currently available.`,"overview","capital-veto-off");
  if(prev.lossState!==cur.lossState)addDecisionEvent(cur.lossState==="BRAIN_REVIEW_PENDING"?"RISK":"READY",`Loss review → ${pretty(cur.lossState)}`,`Previous state: ${pretty(prev.lossState)}.`,"overview",`loss-${cur.lossState}`);
  if(cur.policyEpoch&&prev.policyEpoch&&cur.policyEpoch!==prev.policyEpoch)addDecisionEvent("POLICY",`Nyao policy epoch ${cur.policyEpoch} active`,`Atlas/Nyao moved from policy epoch ${prev.policyEpoch} to ${cur.policyEpoch}.`,"atlas",`epoch-${cur.policyEpoch}`);
  if(cur.lastSuccess&&cur.lastTicket&&cur.lastTicket!==prev.lastTicket)addDecisionEvent("TRADE","Order execution confirmed",`Ticket ${cur.lastTicket} opened on ${state.selectedSymbol||"the selected symbol"}.`,"positions",`trade-${cur.lastTicket}`);
  if(cur.open<prev.open)addDecisionEvent("TRADE","Position lifecycle changed",`${prev.open-cur.open} strategy position${prev.open-cur.open===1?"":"s"} closed; Atlas will reconcile the authoritative outcome ledger.`,"positions",`close-${Date.now()}`);
  if(prev.recovery===0&&cur.recovery>0)addDecisionEvent("RISK","Recovery chain activated",`${cur.recovery} active recovery chain${cur.recovery===1?"":"s"}; composite risk accounting is authoritative.`,"positions","recovery-on");
  if(prev.recovery>0&&cur.recovery===0)addDecisionEvent("TRADE","Recovery chain resolved","The active recovery chain is flat; Atlas will score the completed composite result.","positions","recovery-off");
  if(materiallyChanged(prev.scalpRisk,cur.scalpRisk)||materiallyChanged(prev.zoneRisk,cur.zoneRisk))addDecisionEvent("RISK","Opportunity risk allocation updated",`Scalp ${money(cur.scalpRisk)} · zone ${money(cur.zoneRisk)} · available operating risk ${money(cur.available)}.`,"overview",`risk-${Math.round(cur.scalpRisk)}-${Math.round(cur.zoneRisk)}`)
}
function renderDecisionTimeline(){const el=document.getElementById("decision-timeline");if(!el)return;const events=getDecisionTimeline();el.innerHTML=events.length?events.slice(0,40).map(e=>`<div class="decision-event" onclick="go('${esc(e.action||"overview")}')"><span class="decision-dot ${esc(e.kind)}"></span><div><div class="decision-title">${esc(e.title)}</div><div class="decision-body">${esc(e.body)}</div></div><span class="decision-time">${new Date(e.at).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"})}</span></div>`).join(""):'<div class="observability-empty">Atlas will record the next material decision change.</div>'}
function opportunityStatusClass(status){return status==="READY"?"ready":status==="ACTIVE"?"active":status==="BLOCKED"?"blocked":status==="QUALIFYING"?"qualifying":""}
function opportunityBadgeClass(status){return status==="READY"||status==="ACTIVE"?"ok":status==="BLOCKED"?"bad":"warn"}
function opportunityRow(name,value,status,next,meta,view){return `<div class="opportunity-item ${opportunityStatusClass(status)}" onclick="go('${view}')"><div><div class="opportunity-name">${esc(name)}</div><div class="opportunity-value">${esc(value)}</div></div><div class="opportunity-next"><strong>Next:</strong> ${esc(next)}<div class="opportunity-meta">${esc(meta)}</div></div><span class="badge ${opportunityBadgeClass(status)} opportunity-status">${esc(status)}</span></div>`}
function scalpOpportunity(side){
  const s=state.status||{},cap=state.zonePlan?.capital_sizing||{},upper=side.toUpperCase();
  const score=Number(s[`${side}_adjusted_score`]??s[`${side}_score`]??0);
  const threshold=Number(s[`${side}_effective_threshold`]??s[`runtime_min_${side}_signal_score`]??0);
  const eligible=!!s[`${side}_entry_eligible`];
  const reason=String(s[`${side}_block_reason`]||"").toUpperCase();
  const risk=Number(cap.approved_scalp_risk_amount||0);
  const zoneState=String(s.zone_directive_state||"").toUpperCase();
  const zoneSide=String(s.zone_side||"NONE").toUpperCase();
  const zoneAware=Boolean(s.zone_aware_scalping_active||(zoneState==="ZONE_AWARE_SCALP"&&!s.zone_scalp_suspended));
  const contextual=zoneAware&&zoneSide!=="NONE";
  const counter=contextual&&zoneSide!==upper;
  const aligned=contextual&&zoneSide===upper;
  const label=contextual?`${upper} SCALP · ${counter?"COUNTER-ZONE":"ZONE-ALIGNED"}`:`${upper} SCALP`;
  let status=eligible?"READY":"WATCHING";
  let next=eligible?"All deterministic entry gates currently pass.":"Waiting for the next eligible scalp condition.";
  if(reason==="SCORE_BELOW_THRESHOLD"||score<threshold){
    next=`Score must first reach ${fmt(threshold,2)}; currently ${fmt(score,2)}.${counter?" Counter-zone evidence requirements apply after the base signal gate.":""}`;
  }else if(reason==="COUNTER_ZONE_EVIDENCE_INSUFFICIENT"){
    status="QUALIFYING";next="Base signal qualifies, but the additional counter-zone evidence premium has not cleared yet.";
  }else if(reason==="COUNTER_ZONE_COMMIT_PROXIMITY"){
    status="BLOCKED";next=`The ${zoneSide} zone campaign is too close to commitment for a fresh ${upper} counter-zone scalp.`;
  }else if(reason==="COUNTER_ZONE_SIGNAL_READY"){
    status=eligible?"READY":"QUALIFYING";next=eligible?"Counter-zone evidence is qualified and all remaining Nyao gates pass.":"Counter-zone evidence is qualified; another execution gate is still pending.";
  }else if(reason.includes("COST")||s.scalp_cost_feasible===false){
    next=`Execution economics must recover (${pretty(s.scalp_structure_reason||reason||"cost gate")}).`;
  }else if(reason.includes("CAPITAL")||s.capital_veto_new_risk){
    status="BLOCKED";next="Atlas capital authority must reopen fresh risk.";
  }else if(reason==="ATLAS_ZONE_MODE"){
    status="BLOCKED";next="The committed zone campaign currently owns fresh-entry authority.";
  }else if(reason&&reason!=="NONE"&&reason!=="INITIALIZED"){
    status="BLOCKED";next=pretty(reason);
  }
  const contextMeta=counter?`${zoneSide} zone · counter-zone rules`:aligned?`${zoneSide} zone · aligned rules`:"normal scalp rules";
  return opportunityRow(label,`${fmt(score,2)} / ${fmt(threshold,2)}`,status,next,`Current opportunity limit ${money(risk)} · ${contextMeta} · ${pretty(reason||"NO BLOCK")}`,"market");
}
function zoneOpportunity(){
  const s=state.status||{},zp=state.zonePlan||{},plan=zp.zone_plan||null,cap=zp.capital_sizing||{};if(!plan&&!s.zone_plan_id)return opportunityRow("ZONE CAMPAIGN","NO PRIORITY ZONE","WATCHING","Wait for Atlas to detect and qualify higher-timeframe structure.",`Current zone opportunity limit ${money(cap.approved_zone_risk_amount||0)}`,"analysis");
  const ownership=zoneOwnershipState(s);
  const side=String(plan?.side||s.zone_side||ownership.liveZonePositions[0]?.type||"ZONE"),confirm=Number(s.zone_confirmation_score??plan?.confirmation?.zone_confirmation?.combined_score??0),ct=Number(s.zone_confirmation_threshold??plan?.confirmation?.zone_confirmation?.threshold??0),dir=Number(s.zone_directional_score||0),dt=Number(s.zone_minimum_directional_score||0),spreadOk=s.zone_spread_within_limit!==false,stateName=String(s.zone_directive_state||zp.execution_lane||""),committed=ownership.owns;
  let status=committed?"ACTIVE":"WATCHING",needs=[];if(ct>0&&confirm<ct)needs.push(`confirmation ${fmt(confirm,1)} → ${fmt(ct,1)}`);if(dt>0&&dir<dt)needs.push(`directional ${fmt(dir,2)} → ${fmt(dt,2)}`);if(!spreadOk)needs.push(`spread must return inside adaptive cap`);if(s.capital_veto_new_risk)needs.push("capital authority");if(!needs.length&&!committed){status="READY";needs.push("Atlas/Nyao commit boundary")}
  return opportunityRow(`${side} ZONE CAMPAIGN`,ct>0?`${fmt(confirm,1)} / ${fmt(ct,1)}`:pretty(stateName||"DETECTED"),status,committed?"Campaign has committed execution priority.":needs.join(" · "),`Directional ${fmt(dir,2)} / ${fmt(dt,2)} · ${spreadOk?"cost PASS":"cost BLOCK"} · limit ${money(cap.approved_zone_risk_amount||0)}`,"analysis")
}
function recoveryOpportunity(){const s=state.status||{},rr=state.recoveryRisk||{},chains=rr.active_chains||[];if(!chains.length&&!Number(s.active_hedge_chains||0))return opportunityRow("RECOVERY","STANDBY","WATCHING","No active recovery chain; Atlas will create recovery authority only from an eligible root lifecycle.","Composite-chain risk remains isolated from fresh opportunity budgets.","positions");const c=chains[0]||{},remaining=Number(c.hard_loss_budget_remaining_usd),ceiling=Number(c.hard_loss_budget_usd);return opportunityRow("RECOVERY CHAIN",money(c.mark_to_market||s.hedge_chain_floating_pl||0),"ACTIVE",Number.isFinite(remaining)?`${money(remaining)} chain risk remains inside the frozen ceiling.`:"Manage the active chain inside its frozen Atlas authority.",`Ceiling ${money(ceiling||0)} · ${Number(c.member_count||0)} member(s)`,"positions")}
function renderOpportunityQueue(){const el=document.getElementById("opportunity-queue"),badge=document.getElementById("opportunity-queue-badge"),summary=document.getElementById("opportunity-queue-summary");if(!el)return;const s=state.status||{},cap=state.zonePlan?.capital_sizing||{};el.innerHTML=[scalpOpportunity("buy"),scalpOpportunity("sell"),zoneOpportunity(),recoveryOpportunity()].join("");const anyReady=!!s.buy_entry_eligible||!!s.sell_entry_eligible||String(s.zone_directive_state||"").includes("ZONE_CAMPAIGN");badge.textContent=anyReady?"ACTIONABLE":"SCANNING";badge.className="badge "+(anyReady?"ok":"info");const alloc=cap.portfolio_allocation||{};summary.innerHTML=`<span><strong>${money(alloc.remaining_operating_risk_amount||0)}</strong> operating capacity</span><span>·</span><span><strong>${money(alloc.reserved_active_risk_amount||0)}</strong> reserved</span><span>·</span><span>Hard ceiling <strong>${money(alloc.portfolio_hard_ceiling_amount||0)}</strong></span>`}

async function loadSymbols(){
  try{
    const data=await api("/api/v1/atlas/symbols");
    state.symbols=data.symbols||[];

    const stored=localStorage.getItem("atlasSelectedSymbol");
    const available=state.symbols.map(x=>x.symbol);
    if(!state.selectedSymbol){
      if(stored && available.includes(stored))state.selectedSymbol=stored;
      else state.selectedSymbol=data.default_symbol||available[0]||null;
    }

    const select=document.getElementById("symbol-select");
    select.innerHTML=state.symbols.length
      ? state.symbols.map(item=>{
          const status=item.connected?"●":"○";
          return `<option value="${esc(item.symbol)}">${status} ${esc(item.symbol)}</option>`;
        }).join("")
      : '<option value="">No symbols</option>';

    if(state.selectedSymbol)select.value=state.selectedSymbol;
  }catch(e){
    console.warn("Symbol discovery failed",e);
  }
}

async function switchSymbol(symbol){
  if(!symbol || symbol===state.selectedSymbol)return;
  state.selectedSymbol=symbol;
  localStorage.setItem("atlasSelectedSymbol",symbol);

  state.status=null;
  state.command=null;
  state.intelligence=null;
  state.proposal=null;
  state.review=null;
  state.supervised=null;
  state.preflight=null;
  state.execution=null;
  state.ack=null;
  state.executionEvents=null;
  state.epochs=null;
  state.outcomes=null;
  state.audit=null;
  state.llmCycle=null;
  state.responsiveness=null;
  state.candles=null;
  state.zoneMap=null;
  state.zonePlan=null;
  state.dirty={};

  const controls=document.getElementById("runtime-controls");
  if(controls)controls.innerHTML="";

  toast(`Switched Atlas context to ${symbol}.`);
  await loadCore();
  await loadRiskAppetite();
  await loadIntelligence();
  await loadParameterIntelligence();
  await loadArm();
  await loadLlmCycle();
  await loadResponsiveness();
  await loadMarketCandles();
  await loadZoneMap();
  await loadProposal();
  await loadHistory();
  renderAll();
  renderControls();
}

function accountType(){
  const s=state.status||{};
  return text(s.account_type||s.account_trade_mode||s.trade_mode||s.account_mode,"ACCOUNT CONNECTED").toUpperCase();
}
function updateChrome(){
  const s=state.status||{}, c=state.command||{};
  const connected=s.connected!==false && !!state.status;
  const symbol=text(s.symbol||state.selectedSymbol,"—");
  const select=document.getElementById("symbol-select");
  if(select && state.selectedSymbol)select.value=state.selectedSymbol;
  document.getElementById("side-dot").className="dot "+(connected?"ok":"bad");
  document.getElementById("side-connection").textContent=connected?"Connected":"Offline";
  document.getElementById("side-symbol").textContent=symbol;
  const ms=String(s.market_session_state||"UNKNOWN");const mp=document.getElementById("market-session-pill");if(mp){mp.textContent=`MARKET ${pretty(ms)}`;mp.className=`pill ${ms==="CLOSED"?"bad":ms==="CLOSING_SOON"?"warn":""}`};
  document.getElementById("account-pill").textContent=accountType();
  document.getElementById("epoch-pill").textContent="Epoch "+text(c.policy_epoch??s.policy_epoch);
  document.getElementById("command-pill").textContent="Command "+text(c.command_version??s.applied_command_version);
}

function currentRisk(){
  const p=state.proposal||{};
  const i=state.intelligence||{};
  return p.risk?.state||p.review_summary?.risk_state||i.risk_governor?.state||i.risk?.state||"—";
}
function zoneOwnershipState(s){
  const positions=Array.isArray(s.positions)?s.positions:[];
  const liveZonePositions=positions.filter(p=>{
    const origin=String(p?.order_origin||"").toUpperCase();
    const gate=String(p?.entry_gate_mode||"").toUpperCase();
    return origin==="ATLAS_ZONE"||gate==="ATLAS_ZONE"||Boolean(p?.zone_plan_id);
  });
  const blockers=[s.buy_block_reason,s.sell_block_reason].map(x=>String(x||"").toUpperCase());
  const directive=String(s.zone_directive_state||"").toUpperCase();
  const scalpSuspended=Boolean(s.zone_scalp_suspended);
  const owns=Boolean(
    liveZonePositions.length ||
    scalpSuspended ||
    blockers.includes("ATLAS_ZONE_MODE") ||
    directive.includes("ZONE_CAMPAIGN")
  );
  return {owns,liveZonePositions,scalpSuspended,directive};
}
function renderOverview(){
  const s=state.status||{}, c=state.command||{}, p=state.proposal||{};
  const zp=state.zonePlan||{}, activePlan=zp.zone_plan||null, capital=zp.capital_sizing||{};
  const cycle=state.llmCycle||{};
  const connected=!!state.status && s.connected!==false;
  const applied=s.applied_command_version;
  const synchronized=applied==null || c.command_version==null ? connected : Number(applied)===Number(c.command_version);
  const zoneAwarePlanned=Boolean(zp.zone_aware_scalping_active);
  const zoneAware=Boolean(
    s.zone_aware_scalping_active ||
    (
      s.zone_directive_fresh!==false &&
      !s.zone_scalp_suspended &&
      ["ZONE_AWARE_SCALP","ZONE_CAPITAL_INFEASIBLE"].includes(String(s.zone_directive_state||"").toUpperCase())
    )
  );
  const zoneOwnership=zoneOwnershipState(s);
  const zoneMode=Boolean(zoneOwnership.owns&&!zoneAware);
  const liveZoneSide=zoneOwnership.liveZonePositions[0]?.type;
  const side=text(activePlan?.side||s.zone_side||liveZoneSide,"ZONE");
  const executionLane=zoneAware?"ZONE-AWARE SCALP":zoneMode?"ZONE CAMPAIGN":"NORMAL SCALP";
  const liveCount=Number(s.strategy_open_positions??s.open_positions??0), stagedCount=Number(s.working_limit_orders||0);
  const permissionsOk=s.terminal_algo_trading_allowed!==false&&s.ea_trading_allowed!==false&&s.account_trade_allowed!==false&&s.account_expert_trading_allowed!==false;
  const confirmed=Boolean((zp.directive_preview||{}).zone_entry_allowed);
  const campaignRisk=Number(activePlan?.risk?.account_risk_pct||capital.approved_zone_risk_pct||0);
  const modeName=zoneAware?`${side} ZONE-AWARE SCALP`:zoneMode?`${side} ZONE CAMPAIGN`:"NORMAL SCALP";
  const setGlobal=(id,value)=>{const el=document.getElementById(id);if(el)el.textContent=value};
  setGlobal("global-status-symbol",text(s.symbol||state.selectedSymbol));
  setGlobal("global-status-mode",modeName);
  setGlobal("global-status-positions",`${liveCount} live`);
  const alloc=capital.portfolio_allocation||{};
  setGlobal("global-status-risk",Number.isFinite(Number(alloc.remaining_operating_risk_amount))?`${money(alloc.remaining_operating_risk_amount)} free`:"—");
  setGlobal("global-status-brain",cycle.running?"REVIEWING":cycle.enabled&&Number.isFinite(Number(cycle.seconds_until_next_run))?`REVIEW ${age(cycle.seconds_until_next_run)}`:"IDLE");
  setGlobal("global-status-health",connected&&permissionsOk&&s.zone_directive_fresh!==false?"HEALTHY":connected?"DEGRADED":"OFFLINE");
  const gsd=document.getElementById("global-status-dot");if(gsd)gsd.className="dot "+(connected?"ok":"bad");
  document.getElementById("hero-state").textContent=!connected?"Nyao is offline":String(s.market_session_state||"")==="CLOSED"?"Market is closed":zoneAware?`${side} zone context guiding scalps`:zoneMode?`${side} zone campaign owns execution`:"Atlas is scanning for scalps";
  document.getElementById("hero-copy").textContent=!connected
    ?"Atlas cannot verify market state or execution authority."
    :String(s.market_session_state||"")==="CLOSED"
      ?`Broker session is closed for ${text(s.symbol)}. Existing state remains observable; no fresh broker execution is possible until the next session opens.`
    :zoneAware
      ?`A qualified ${side} zone is informing scalp direction, but the full zone campaign does not own execution. Nyao keeps normal scalp thresholds, costs and Atlas risk limits.`
      :zoneMode
        ?`${liveCount} live position${liveCount===1?"":"s"} and ${stagedCount} staged entr${stagedCount===1?"y":"ies"}. Ordinary scalping is paused while this campaign owns the risk budget.`
        :"No priority zone currently owns execution. Nyao may scalp when Atlas direction, cost, signal and capital gates agree.";
  const modeBadge=document.getElementById("hero-mode-badge");modeBadge.textContent=connected?modeName:"OFFLINE";modeBadge.className="badge "+(connected?(zoneMode?"info":"ok"):"bad");
  document.getElementById("hero-symbol").textContent=text(s.symbol||state.selectedSymbol);
  document.getElementById("hero-market-state").textContent=zoneAware?`${side} aligned preferred · counter-zone conditional`:zoneMode?(confirmed?"zone confirmed":"awaiting confirmation"):(s.scalp_cost_ratio_feasible===false?"spread cost blocked":s.scalp_structure_feasible===false?"structure blocked":"scalp scan active");
  document.getElementById("hero-bridge").textContent=s.zone_directive_fresh===false?"stale":"live";
  document.getElementById("hero-risk").textContent=modeName;
  document.getElementById("hero-policy").textContent=campaignRisk>0?`${fmt(campaignRisk,3)}% equity`:capital.approved_scalp_risk_pct>0?`${fmt(capital.approved_scalp_risk_pct,3)}% equity`:"No new risk";
  document.getElementById("hero-open").textContent=`${liveCount} live · ${stagedCount} staged`;
  document.getElementById("hero-chains").textContent=cycle.running?"Running now":cycle.enabled&&Number.isFinite(Number(cycle.seconds_until_next_run))?age(cycle.seconds_until_next_run):"Not scheduled";
  const liveBadge=document.getElementById("overview-live-badge");liveBadge.textContent=connected&&permissionsOk?"SYSTEM LIVE":"ATTENTION";liveBadge.className="badge "+(connected&&permissionsOk?"ok":"bad");
  document.getElementById("balance").textContent=money(s.balance);
  document.getElementById("equity").textContent="Equity "+money(s.equity);
  const pl=s.strategy_floating_pl??s.floating_profit;
  const pel=document.getElementById("floating");pel.textContent=money(pl);pel.className="value "+(Number(pl)>0?"pos":Number(pl)<0?"neg":"");
  document.getElementById("drawdown").textContent=`Drawdown ${fmt(s.equity_drawdown_pct)}%`;
  document.getElementById("market-label").textContent=`Live market · ${text(s.symbol)}`;
  document.getElementById("market-price").textContent=`${text(s.bid)} / ${text(s.ask)}`;
  document.getElementById("market-spread").textContent=`Spread ${fmt(s.spread_points,1)} pts`;
  document.getElementById("protect-positions").textContent=text(s.strategy_open_positions??s.open_positions,0);
  document.getElementById("protect-recovery").textContent=text(s.active_hedge_chains,0);
  document.getElementById("protect-basket").textContent=`${fmt(s.basket_loss_pct)}%`;
  document.getElementById("protect-duplicate").textContent=s.runtime_enable_duplicate_distance_filter===false?"OFF":"ON";
  const riskUnits=state.riskUnits||{};
  document.getElementById("protect-risk-streak").textContent=`${text(riskUnits.consecutive_completed_loss_units,0)} completed unit${Number(riskUnits.consecutive_completed_loss_units||0)===1?"":"s"}`;
  const recoveryLedger=state.recoveryRisk||{};
  const lastRecoverySizing=recoveryLedger.last_recovery_sizing||{};
  const recoveryReason=text(lastRecoverySizing.reason||s.recovery_sizing_reason,"NOT EVALUATED");
  const recoveryFinalLot=Number(lastRecoverySizing.final_lot||s.recovery_final_lot||0);
  document.getElementById("protect-recovery-sizing").textContent=recoveryFinalLot>0?`${fmt(recoveryFinalLot,2)} lot · ${pretty(recoveryReason)}`:pretty(recoveryReason);
  document.getElementById("protect-unit-risk").textContent=Number(lastRecoverySizing.original_unit_risk_usd)>0?money(lastRecoverySizing.original_unit_risk_usd):"—";
  document.getElementById("protect-chain-ceiling").textContent=Number(lastRecoverySizing.chain_budget_usd)>0?`${money(lastRecoverySizing.chain_budget_usd)} · ${fmt(lastRecoverySizing.unit_budget_multiplier||0,2)}×`:"—";
  const portfolioAllocation=capital.portfolio_allocation||{};
  document.getElementById("protect-portfolio-reserved").textContent=money(portfolioAllocation.reserved_active_risk_amount||0);
  document.getElementById("protect-portfolio-available").textContent=money(portfolioAllocation.remaining_operating_risk_amount||0);
  const activeComposite=(riskUnits.units||[]).filter(u=>u.state==="ACTIVE"&&u.unit_type!=="STANDALONE_TRADE");
  const completedComposite=(riskUnits.units||[]).filter(u=>u.state==="COMPLETE"&&u.unit_type!=="STANDALONE_TRADE");
  const latestComposite=completedComposite.length?completedComposite[completedComposite.length-1]:null;
  document.getElementById("protect-composite-active").textContent=activeComposite.length?activeComposite.map(u=>pretty(u.unit_type)).join(" · "):"NONE";
  document.getElementById("protect-composite-latest").textContent=latestComposite?`${pretty(latestComposite.unit_type)} · ${latestComposite.result_class} · ${money(latestComposite.realized_net_pl)}`:"NONE";
  const chainBudget=Number(lastRecoverySizing.chain_budget_usd||s.recovery_chain_budget_usd||0);
  const activeLedgerChain=(recoveryLedger.active_chains||[])[0]||{};
  const budgetRemaining=Number(activeLedgerChain.hard_loss_budget_remaining_usd);
  const recoveryBudgetBasis=text(activeLedgerChain.budget_basis||lastRecoverySizing.budget_basis,"UNOBSERVED");
  document.getElementById("protect-recovery-copy").textContent=activeComposite.length
    ?`${activeComposite.length} composite risk unit${activeComposite.length===1?" is":"s are"} in flight. Member closes remain provisional. Recovery ceiling ${chainBudget>0?money(chainBudget):"unavailable"}${Number(lastRecoverySizing.original_unit_risk_usd)>0?` from ${money(lastRecoverySizing.original_unit_risk_usd)} original unit risk × ${fmt(lastRecoverySizing.unit_budget_multiplier||0,2)}`:""}${Number.isFinite(budgetRemaining)?` · ${money(budgetRemaining)} remaining`:""}. Budget basis: ${pretty(recoveryBudgetBasis)}. Portfolio ceiling remains ${money(recoveryLedger.portfolio_hard_risk_budget_usd||0)}. Last limiter: ${pretty(recoveryReason)}.`
    :`No composite risk unit is currently in flight. Completed loss streak is ${text(riskUnits.consecutive_completed_loss_units,0)} risk unit(s); recovery-chain and zone-campaign legs are scored only as their completed composite unit.`;
  const ack=state.ack;
  document.getElementById("ack-state").textContent=!connected?"OFFLINE":permissionsOk&&s.zone_directive_fresh!==false?"HEALTHY":"CHECK REQUIRED";
  document.getElementById("ack-state").className="value small "+(!connected||!permissionsOk?"neg":"pos");
  document.getElementById("ack-detail").textContent=permissionsOk?`Nyao connected · ${ack?.state||latestAckState()} acknowledgement`:"One or more MT5 trading permissions are disabled";

  // P3.23 dashboard: make execution ownership, structural context, hard capital
  // authority and Gemini's Nyao-policy authority visibly separate.
  const laneEl=document.getElementById("authority-lane");
  laneEl.textContent=executionLane;
  laneEl.className="authority-main "+(zoneAware?"lane-zone-aware":zoneMode?"lane-zone":"lane-normal");
  const laneBadge=document.getElementById("authority-lane-badge");
  laneBadge.textContent=zoneMode?"ZONE OWNS ENTRIES":zoneAware?"SCALP + ZONE CONTEXT":"SCALP OWNS ENTRIES";
  laneBadge.className="badge "+(zoneMode?"info":zoneAware?"warn":"ok");
  document.getElementById("authority-lane-copy").textContent=zoneMode
    ?"A broker-feasible zone campaign owns fresh-entry authority; ordinary scalp entries are suspended."
    :zoneAware
      ?`The ${side} zone remains read-only structural context. ${side} scalps may qualify; counter-zone scalps remain conditional: they require stronger evidence, reduced risk authority, and remain subject to campaign-proximity blocking.`
      :"Ordinary Nyao scalping owns fresh-entry authority. Zone analysis continues in the background.";
  document.getElementById("authority-scalp").textContent=zoneMode?"SUSPENDED":zoneAware?`${side} ALIGNED ONLY`:"ACTIVE";
  document.getElementById("authority-zone").textContent=zoneMode?"ACTIVE":activePlan?(Number(activePlan.entries?.length||0)>0?"ARMED / WAITING":"CONTEXT ONLY"):"MONITORING";

  const sourceZone=activePlan?.source_zone||{};
  const zoneScore=Number(sourceZone.score||0);
  const zoneLabel=activePlan?`${side} · ${text(sourceZone.timeframe,"—")} ${pretty(sourceZone.kind||"ZONE")}`:"NO PRIORITY ZONE";
  document.getElementById("context-zone").textContent=zoneLabel;
  const contextBadge=document.getElementById("context-zone-badge");
  contextBadge.textContent=activePlan?text(sourceZone.status||zp.state,"ZONE"):"SCANNING";
  contextBadge.className="badge "+(activePlan?"info":"warn");
  document.getElementById("context-zone-copy").textContent=activePlan
    ?`${fmt(sourceZone.low,3)} – ${fmt(sourceZone.high,3)}${zoneScore>0?` · score ${fmt(zoneScore,1)}`:""}. Gemini receives this as read-only scalp context.`
    :"No active priority-zone context is constraining the current scalp lane.";
  const htfStructure=text(state.zoneMap?.composite_bias,"NEUTRAL");
  const liveThesis=text(state.intelligence?.regime?.direction,"NEUTRAL");
  const normalizeDirection=value=>{const v=String(value||"").toUpperCase();return v.includes("BEAR")||v==="SELL"?"BEARISH":v.includes("BULL")||v==="BUY"?"BULLISH":v.includes("NEUTRAL")||v==="MIXED"?"NEUTRAL":v};
  const htfDir=normalizeDirection(htfStructure), liveDir=normalizeDirection(liveThesis);
  const thesisRelation=zoneAware?`${side} ZONE CONSTRAINT`:zoneMode?`${side} CAMPAIGN`:htfDir!=="NEUTRAL"&&liveDir!=="NEUTRAL"?(htfDir===liveDir?"ALIGNED":"CONFLICTING"):"NO CONFLICT SIGNAL";
  document.getElementById("context-bias").textContent=pretty(htfStructure);
  document.getElementById("context-alignment").textContent=thesisRelation;
  document.getElementById("context-zone-copy").textContent=activePlan
    ?`${fmt(sourceZone.low,3)} – ${fmt(sourceZone.high,3)}${zoneScore>0?` · score ${fmt(zoneScore,1)}`:""}. HTF structure ${pretty(htfStructure)}; live Atlas thesis ${pretty(liveThesis)}. Gemini receives the zone as read-only scalp context.`
    :`No priority-zone constraint. HTF structure is ${pretty(htfStructure)} while the live Atlas thesis is ${pretty(liveThesis)}${thesisRelation==="CONFLICTING"?" — directional layers currently disagree.":"."}`;

  const simulated=capital.demo_capital_simulation||{};
  const simActive=Boolean(simulated.active);
  const capitalPresent=Boolean(capital&&Object.keys(capital).length&&capital.version);
  const capitalExplicitVeto=capitalPresent&&capital.veto_new_risk===true;
  const capitalExplicitAllow=capitalPresent&&capital.veto_new_risk===false;
  const statusHasCapitalDecision=typeof s.capital_veto_new_risk==="boolean";
  const capitalMismatch=capitalPresent&&statusHasCapitalDecision&&Boolean(s.capital_veto_new_risk)!==Boolean(capital.veto_new_risk);
  const capitalSyncing=!capitalPresent||!capitalExplicitVeto&&!capitalExplicitAllow||capitalMismatch;
  const riskCapital=Number(capital.risk_capital||capital.real_risk_capital||s.equity||0);
  const regimeName=text(capital.capital_regime||capital.regime,"—");
  const vetoReasons=Array.isArray(capital.veto_reasons)?capital.veto_reasons:[];
  const allocation=capital.portfolio_allocation||{};
  const allocationState=text(allocation.allocation_state,"AVAILABLE");
  const preLossProtection=capital.loss_protection||{};
  const recoveryProbeInFlight=text(preLossProtection.state)==="RECOVERY_PROBE"&&Number(s.strategy_open_positions||0)>0;
  const fullyAllocated=allocationState==="FULLY_ALLOCATED";
  const partiallyAllocated=allocationState==="PARTIALLY_ALLOCATED";
  const capitalBadge=document.getElementById("capital-regime-badge");
  capitalBadge.textContent=capitalSyncing?"SYNCING":recoveryProbeInFlight?"RECOVERY PROBE · IN FLIGHT":fullyAllocated?"FULLY ALLOCATED":partiallyAllocated?"PARTIALLY ALLOCATED":capitalExplicitVeto?"CAPITAL VETO":simActive?`DEMO ${pretty(regimeName)}`:pretty(regimeName);
  capitalBadge.className="badge "+(capitalSyncing?"warn":recoveryProbeInFlight||partiallyAllocated?"info":fullyAllocated?"warn":capitalExplicitVeto?"bad":simActive?"warn":"ok");
  document.getElementById("capital-risk-base").textContent=money(riskCapital);
  const portfolioHard=Number(allocation.portfolio_hard_ceiling_amount||capital.maximum_total_strategy_risk_amount||0);
  const operatingCap=Number(allocation.operating_risk_ceiling_amount||portfolioHard);
  const reservedRisk=Number(allocation.reserved_active_risk_amount||0);
  const availableRisk=Number(allocation.remaining_operating_risk_amount||0);
  document.getElementById("capital-risk-copy").textContent=capitalSyncing
    ?"Capital state is reconciling across Nyao telemetry and Atlas sizing. Last complete budget is not treated as a fresh veto."
    :recoveryProbeInFlight
      ?"A reduced-risk recovery probe is in flight. Independent fresh risk remains intentionally paused until the composite probe resolves so the probe remains valid evidence; only the final composite chain result can break or escalate the loss streak."
      :capitalExplicitVeto
        ?`New risk is explicitly vetoed${vetoReasons.length?`: ${vetoReasons.map(pretty).join(" · ")}`:" by the capital governor."}`
        :partiallyAllocated
          ?`Concurrent allocator: ${money(reservedRisk)} reserved across active risk units · ${money(availableRisk)} operating capacity remains (${money(operatingCap)} operating / ${money(portfolioHard)} hard ceiling). Existing trades do not automatically block independent opportunities.`
          :simActive
            ?`Demo simulated risk capital; MT5 equity remains ${money(s.equity)}. Hard Atlas limits still apply.`
            :`Atlas risk capital · ${money(availableRisk||operatingCap)} operating capacity available · portfolio hard ceiling ${money(portfolioHard)}.`;
  const scalpAmount=Number(capital.approved_scalp_risk_amount||0), zoneAmount=Number(capital.approved_zone_risk_amount||0);
  const scalpPct=Number(capital.approved_scalp_risk_pct||0), zonePct=Number(capital.approved_zone_risk_pct||0);
  const lossProtection=capital.loss_protection||{};
  const protectionState=text(lossProtection.state,"INACTIVE");
  if(!capitalSyncing&&protectionState==="BRAIN_REVIEW_PENDING"){
    capitalBadge.textContent="BRAIN REVIEW · PENDING";
    capitalBadge.className="badge warn";
    document.getElementById("capital-risk-copy").textContent=`${text(lossProtection.consecutive_losses,0)} consecutive completed losses triggered an immediate Gemini review. Fresh risk is paused only while the review is in flight; there is no 15/30/60-minute timeout and no automatic reduced-lot probation trade. HOLD or a validated policy update releases normal opportunity sizing.`;
  }else if(!capitalSyncing&&protectionState==="REVIEW_COMPLETE"){
    capitalBadge.textContent="BRAIN REVIEW · COMPLETE";
    capitalBadge.className="badge ok";
    document.getElementById("capital-risk-copy").textContent=`Loss-streak review completed at ${text(lossProtection.brain_reviewed_streak,lossProtection.consecutive_losses||0)} losses. Trading may continue under normal deterministic drawdown, exposure, broker and market-risk gates.`;
  }else if(!capitalSyncing&&protectionState==="RECOVERY_PROBE"){
    const release=lossProtection.policy_release||{};
    const adapted=lossProtection.release_reason==="MATERIAL_POLICY_RUNTIME_CONFIRMED";
    capitalBadge.textContent=adapted?"POLICY-ADAPTED RECOVERY":"RECOVERY PROBE";
    capitalBadge.className="badge warn";
    const probeTarget=Number(capital.recovery_probe_target_risk_pct||lossProtection.recovery_probe_scalp_risk_pct||scalpPct||0);
    const probeCap=Number(capital.recovery_probe_max_executable_risk_pct||lossProtection.recovery_probe_max_executable_risk_pct||0);
    const probeMinPct=Number(s.recovery_probe_minimum_executable_risk_pct||0);
    const probeMinUsd=Number(s.recovery_probe_minimum_executable_risk_amount||0);
    const probeReason=String(s.recovery_probe_feasibility_reason||"NOT_EVALUATED");
    const probeBrokerNote=probeReason==="BROKER_MINIMUM_OVERRIDE_WITHIN_PROBE_CAP"
      ?` Broker minimum requires ${money(probeMinUsd)} (${fmt(probeMinPct,3)}%); bounded minimum-volume override is active within the ${fmt(probeCap,3)}% probe cap.`
      :probeReason==="MIN_VOLUME_RISK_EXCEEDS_PROBE_CAP"
        ?` Broker minimum would risk ${money(probeMinUsd)} (${fmt(probeMinPct,3)}%), above the ${fmt(probeCap,3)}% recovery cap, so the probe remains unexecutable.`
        :` If ${fmt(probeTarget,3)}% is below broker minimum size, Atlas may use the minimum volume only while actual stop risk stays ≤ ${fmt(probeCap,3)}%.`;
    document.getElementById("capital-risk-copy").textContent=(adapted
      ?`Epoch ${text(release.policy_epoch)} is runtime-confirmed after the latest loss and materially changed fresh-entry policy (${(release.material_controls||[]).map(pretty).join(", ")||"entry controls"}). The old loss timer was released; target probe risk is ${fmt(probeTarget,3)}%. The ${text(lossProtection.consecutive_losses,0)} prior losses remain evidence; zone risk stays zero.`
      :`Loss-protection timer completed. Target scalp probe risk is ${fmt(probeTarget,3)}%; zone risk remains zero until the streak breaks.`)+probeBrokerNote;
  }
  document.getElementById("capital-scalp-budget").textContent=capitalSyncing?"SYNCING":capitalExplicitVeto?"0.000% · VETOED":scalpAmount>0?`${money(scalpAmount)} · ${fmt(scalpPct,3)}%`:`${fmt(scalpPct,3)}%`;
  document.getElementById("capital-zone-budget").textContent=capitalSyncing?"SYNCING":capitalExplicitVeto?"0.000% · VETOED":zoneAmount>0?`${money(zoneAmount)} · ${fmt(zonePct,3)}%`:`${fmt(zonePct,3)}%`;

  const auto=true;
  const brainBadge=document.getElementById("brain-mode-badge");
  brainBadge.textContent="EVENT-DRIVEN AUTONOMOUS";
  brainBadge.className="badge ok";
  const brainLifecycle=text(cycle.last_auto_apply_status||p.lifecycle?.state||p.review_state,"NO CHANGE");
  const brainStateLabel=brainLifecycle==="MINIMUM_DWELL_ACTIVE"?"STABILITY HOLD":brainLifecycle==="CONSENSUS_NOT_READY"?"BUILDING CONSENSUS":brainLifecycle==="DEFERRED_ACTIVE_ZONE_PLAN"?"ACTIVATION DEFERRED":brainLifecycle==="APPLIED"?"POLICY ACTIVE":pretty(brainLifecycle);
  document.getElementById("brain-policy-state").textContent=brainStateLabel;
  document.getElementById("brain-policy-copy").textContent=zoneMode
    ?"Gemini can continue reasoning about Nyao policy, but a new policy waits for the live zone campaign boundary before activation."
    :zoneAware
      ?`Gemini is allowed to use the ${side} zone as scalp context while Atlas keeps zone construction and hard risk deterministic.`
      :"Gemini may optimize the full Nyao scalp lifecycle; Atlas retains zone, capital, broker-feasibility and hard-risk authority.";
  document.getElementById("brain-epoch").textContent=text(c.policy_epoch??s.policy_epoch);
  document.getElementById("brain-next").textContent=cycle.running?"RUNNING":cycle.enabled&&Number.isFinite(Number(cycle.seconds_until_next_run))?age(cycle.seconds_until_next_run):"NOT SCHEDULED";

  const campaignBadge=document.getElementById("overview-campaign-badge");
  if(activePlan&&zoneAware){
    const ideal=Array.isArray(activePlan.ideal_entries)?activePlan.ideal_entries:[], admitted=Array.isArray(activePlan.entries)?activePlan.entries:[];
    document.getElementById("overview-campaign-title").textContent=`${side} zone context → scalp fallback`;
    document.getElementById("overview-campaign-copy").textContent=`The technical zone remains valid context, but its executable campaign structure is ${admitted.length} leg${admitted.length===1?"":"s"}. Atlas returned fresh-entry authority to context-aware scalping: aligned entries use normal gates while counter-zone entries require stronger evidence and reduced risk.`;
    campaignBadge.textContent="ZONE-AWARE SCALP";campaignBadge.className="badge warn";
    const rows=(ideal.length?ideal:[{leg:1,entry_price:activePlan.source_zone?.low},{leg:2,entry_price:(Number(activePlan.source_zone?.low||0)+Number(activePlan.source_zone?.high||0))/2},{leg:3,entry_price:activePlan.source_zone?.high}]);
    document.getElementById("overview-campaign").innerHTML=rows.map((entry,index)=>`<div class="campaign-leg"><div class="row"><span class="label">IDEAL ENTRY ${entry.leg||index+1}</span><span class="badge ${index<admitted.length?"info":"bad"}">${index<admitted.length?"ADMITTED":"NOT EXECUTABLE"}</span></div><div class="campaign-price">${fmt(entry.entry_price,3)}</div><div class="muted">Zone geometry preserved · scalp fallback does not convert this into a zone order</div></div>`).join("");
  }else if(activePlan){
    const entries=Array.isArray(activePlan.entries)?activePlan.entries:[],targets=Array.isArray(activePlan.take_profits)?activePlan.take_profits:[];
    document.getElementById("overview-campaign-title").textContent=`${side} from ${text(activePlan.source_zone?.timeframe)} ${pretty(activePlan.source_zone?.kind||"ZONE")}`;
    document.getElementById("overview-campaign-copy").textContent=`Shared stop ${fmt(activePlan.stop_loss,3)} · total risk ${fmt(campaignRisk,3)}% · confirmation ${fmt(activePlan.confirmation?.zone_confirmation?.combined_score,1)} / ${fmt(activePlan.confirmation?.zone_confirmation?.threshold,1)}.`;
    campaignBadge.textContent=confirmed?"CONFIRMED":"WAITING";campaignBadge.className="badge "+(confirmed?"ok":"warn");
    document.getElementById("overview-campaign").innerHTML=entries.map((entry,index)=>{const live=index<liveCount,staged=!live&&index<liveCount+stagedCount,target=targets[index];return `<div class="campaign-leg ${live?"live":""}"><div class="row"><span class="label">ENTRY ${entry.leg}</span><span class="badge ${live?"ok":staged?"info":"warn"}">${live?"LIVE":staged?"STAGED":"PLANNED"}</span></div><div class="campaign-price">${fmt(entry.entry_price,3)}</div><div class="muted">${fmt(entry.risk_allocation_pct,0)}% of campaign risk${target?` · TP ${fmt(target.price,3)}`:""}</div></div>`}).join("");
  }else{
    document.getElementById("overview-campaign-title").textContent="No zone campaign active";
    document.getElementById("overview-campaign-copy").textContent="Atlas is monitoring the market and ordinary scalp gates remain authoritative.";
    campaignBadge.textContent="SCANNING";campaignBadge.className="badge info";
    document.getElementById("overview-campaign").innerHTML=[[`BUY signal`,fmt(s.buy_adjusted_score,2)],['SELL signal',fmt(s.sell_adjusted_score,2)],['Capital budget',capitalSyncing?'SYNCING':capitalExplicitVeto?'VETOED':`${fmt(capital.approved_scalp_risk_pct,3)}%`]].map(([label,value])=>`<div class="campaign-leg"><div class="label">${label}</div><div class="campaign-price">${value}</div><div class="muted">Live Atlas gate</div></div>`).join("");
  }

  let attentionTitle="No action needed",attentionCopy="Atlas is operating inside its current authority.";
  if(!connected){attentionTitle="Reconnect Nyao";attentionCopy="Live state is unavailable, so Atlas cannot supervise execution."}
  else if(!permissionsOk){attentionTitle="Enable MT5 trading";attentionCopy="At least one terminal, EA, or account trading permission is disabled."}
  else if(p.lifecycle?.state==="READY_FOR_HUMAN_REVIEW"&&cycle.execution_mode!=="AUTONOMOUS"){attentionTitle="Policy review available";attentionCopy="Atlas has prepared a supervised policy change for your review."}
  else if(zoneAware){attentionTitle="Zone-aware scalping active";attentionCopy=`The full ${side} zone campaign is not executable, so Atlas released the scalp lane while keeping ${side} zone context. Normal scalp thresholds and risk gates still apply.`}
  else if(zoneMode&&!confirmed){attentionTitle="Atlas is waiting";attentionCopy="Price is in a feasible zone campaign, but confirmation has not qualified. Ordinary scalping remains suspended while the zone lane owns fresh-entry authority."}
  document.getElementById("overview-attention-title").textContent=attentionTitle;
  document.getElementById("overview-attention-copy").textContent=attentionCopy;
  document.getElementById("overview-decision-list").innerHTML=[
    permissionsOk?"MT5 execution permissions are available":"MT5 execution permissions need attention",
    zoneMode?`${liveCount} live and ${stagedCount} staged zone entries`:capitalSyncing?"Scalp capital state is syncing":`Scalp capital gate ${capitalExplicitVeto?"is closed":"is available"}`,
    cycle.enabled?`Atlas Brain is event-driven · ${text(cycle.interval_minutes)}m health heartbeat enabled`:"Atlas Brain is event-driven · health heartbeat disabled"
  ].map(item=>`<div class="decision-item">${esc(item)}</div>`).join("");
  renderProposalChanges("overview-changes",p.changed_controls);
  const pb=document.getElementById("proposal-badge");pb.textContent=p.lifecycle?.state||p.review_state||"NO PROPOSAL";pb.className="badge "+badgeClass(pb.textContent);
  const lifecycle=p.lifecycle?.state;
  document.getElementById("overview-proposal-note").textContent=!p.proposal_id
    ? "No proposal loaded."
    : lifecycle==="APPLIED"
      ? `Applied to command ${text(c.command_version)} / policy epoch ${text(c.policy_epoch)} and confirmed by Nyao.`
      : lifecycle==="AUTO_APPLY_DEFERRED_ZONE"
        ? `Queued for automatic activation after the active zone campaign reaches a clean mode boundary. Current policy remains epoch ${text(c.policy_epoch)}; proposed epoch ${text(p.proposed_policy_epoch)} is not applied yet.`
      : lifecycle==="AWAITING_NYAO_ACK"
        ? `Command written for policy epoch ${text(p.proposed_policy_epoch)}; awaiting Nyao acknowledgement.`
        : `${p.selected_candidate||"Candidate"} · proposed epoch ${text(p.proposed_policy_epoch)} · ${Object.keys(p.changed_controls||{}).length} material change(s).`;
}
function renderLiveAnalysis(){
  const s=state.status||{}, i=state.intelligence||{}, regime=i.regime||{}, risk=i.risk||i.risk_governor||{};
  const direction=String(regime.direction||"").toUpperCase();
  const bias=document.getElementById("signal-bias");
  let bt="NEUTRAL / UNCLEAR", bc="bias-neutral";
  if(direction.includes("BULL")){bt="BULLISH";bc="bias-bull"}else if(direction.includes("BEAR")){bt="BEARISH";bc="bias-bear"}else if(direction){bt=pretty(direction)}
  bias.textContent=bt; bias.className="bias-value "+bc;
  document.getElementById("signal-regime").textContent=pretty(regime.regime||"UNKNOWN");
  document.getElementById("signal-volatility").textContent=pretty(regime.volatility||"UNKNOWN");
  document.getElementById("signal-confidence").textContent=i.confidence==null?"—":fmt(i.confidence,1)+"%";
  document.getElementById("signal-risk").textContent=pretty(risk.state||currentRisk());
  document.getElementById("signal-summary").textContent=i.summary||((regime.reasons||[])[0])||"Atlas intelligence has not produced a current assessment yet.";

  const contextBanner=document.getElementById("scalp-context-banner");
  const contextTitle=document.getElementById("scalp-context-title");
  const contextCopy=document.getElementById("scalp-context-copy");
  const livePlan=state.zonePlan||{};
  const liveActivePlan=livePlan.zone_plan||{};
  const plannedZoneAware=Boolean(livePlan.zone_aware_scalping_active);
  const appliedZoneAware=Boolean(
    s.zone_aware_scalping_active ||
    (
      s.zone_directive_fresh!==false &&
      !s.zone_scalp_suspended &&
      ["ZONE_AWARE_SCALP","ZONE_CAPITAL_INFEASIBLE"].includes(String(s.zone_directive_state||"").toUpperCase())
    )
  );
  const contextSide=String(
    s.zone_side ||
    livePlan.zone_aware_scalping_side ||
    liveActivePlan.side ||
    "NONE"
  ).toUpperCase();

  if(contextBanner){
    contextBanner.style.display=(plannedZoneAware||appliedZoneAware)?"block":"none";

    if(appliedZoneAware && ["BUY","SELL"].includes(contextSide)){
      const pressure=Math.max(
        Number(s.zone_confirmation_threshold||0)>0
          ? Number(s.zone_confirmation_score||0)/Number(s.zone_confirmation_threshold) : 0,
        Number(s.zone_minimum_directional_score||0)>0
          ? Number(s.zone_directional_score||0)/Number(s.zone_minimum_directional_score) : 0
      );
      contextTitle.textContent=`${contextSide} ZONE CONTEXT · LIVE IN NYAO`;
      contextCopy.textContent=`Context-aware scalping is applied. ${contextSide} entries are zone-aligned and use normal gates. ${contextSide==="SELL"?"BUY":"SELL"} entries are counter-zone: stronger evidence, reduced risk, and campaign-proximity blocking apply. Commit pressure ${fmt(Math.min(1,Math.max(0,pressure))*100,0)}%.`;
    }else if(plannedZoneAware){
      contextTitle.textContent=`${contextSide} ZONE CONTEXT · AWAITING NYAO SYNC`;
      contextCopy.textContent=`Atlas has planned zone-aware scalping, but Nyao has not yet confirmed that its scalp lane is released. Applied directive: ${pretty(s.zone_directive_state||"UNKNOWN")} · scalp suspended ${s.zone_scalp_suspended?"YES":"NO"}.`;
    }
  }

  const buy=Number(s.buy_score||0), sell=Number(s.sell_score||0);
  const buyAdj=Number(s.buy_adjusted_score||0), sellAdj=Number(s.sell_adjusted_score||0);
  const buyTh=Number(s.buy_effective_threshold??s.runtime_min_buy_signal_score??0), sellTh=Number(s.sell_effective_threshold??s.runtime_min_sell_signal_score??0);
  document.getElementById("signal-buy-score").textContent=buy.toFixed(2);
  document.getElementById("signal-sell-score").textContent=sell.toFixed(2);
  // Net signal penalties can mathematically push a score below zero. Zero is
  // the executable floor, so display that floor and preserve the raw penalty
  // value in the blocker explanation instead of showing contradictory scores.
  document.getElementById("signal-buy-adjusted").textContent=Math.max(0,buyAdj).toFixed(2);
  document.getElementById("signal-sell-adjusted").textContent=Math.max(0,sellAdj).toFixed(2);
  document.getElementById("signal-buy-threshold").textContent=buyTh.toFixed(2);
  document.getElementById("signal-sell-threshold").textContent=sellTh.toFixed(2);
  document.getElementById("signal-buy-bar").style.width=(buyTh>0?Math.min(100,Math.max(0,buy/buyTh*100)):0)+"%";
  document.getElementById("signal-sell-bar").style.width=(sellTh>0?Math.min(100,Math.max(0,sell/sellTh*100)):0)+"%";

  const orderReason=(side,reason)=>{
    const code=Number(s.last_order_retcode||0), direction=String(s.last_order_direction||"").toLowerCase();
    if(direction!==side || !String(reason||"").includes("ORDER"))return pretty(text(reason,"NONE"));
    const descriptions={10026:"Algo trading disabled by broker/server",10027:"Algo trading disabled in MT5 terminal",10018:"Market closed",10019:"Insufficient funds",10030:"Unsupported order filling mode",10016:"Invalid stops"};
    const reasonMap={
      ATLAS_ZONE_MODE:"ZONE CAMPAIGN OWNS FRESH ENTRIES",
      ZONE_CONTEXT_COUNTER_DIRECTION:"COUNTER-ZONE DIRECTION BLOCKED (LEGACY 44.4)",
      COUNTER_ZONE_EVIDENCE_INSUFFICIENT:"COUNTER-ZONE · STRONGER EVIDENCE REQUIRED",
      COUNTER_ZONE_COMMIT_PROXIMITY:"COUNTER-ZONE · ZONE CAMPAIGN NEAR COMMIT",
      COUNTER_ZONE_SIGNAL_READY:"COUNTER-ZONE · QUALIFIED",
      ZONE_CONTEXT_ALIGNED:"ZONE-ALIGNED SCALP"
    };
    const raw=String(reason||"NONE").toUpperCase();
    if(reasonMap[raw])return reasonMap[raw];
    if(code===10016){
      const retry=Number(s.preflight_retry_count||0);
      const slDist=Number(s.preflight_sl_distance_points||0);
      const minDist=Number(s.preflight_min_distance_points||0);
      const safety=Number(s.preflight_retry_safety_points||0);
      const detail=retry?` · retry ${retry} · SL ${fmt(slDist,0)} pts / min ${fmt(minDist,0)} pts · safety +${fmt(safety,0)} pts`:"";
      const detached=s.preflight_detached_stops_fallback_attempted?` · detached-stop test ${s.preflight_detached_stops_fallback_accepted?"PASS":"FAIL"}`:"";
      const protection=s.preflight_protection_state&&s.preflight_protection_state!=="NOT_REQUIRED"?` · ${pretty(s.preflight_protection_state)}`:"";
      return `Invalid stops (MT5 10016)${detail}${detached}${protection}`;
    }
    return descriptions[code]?`${descriptions[code]} (MT5 ${code})`:`${pretty(text(reason,"NONE"))}${code?` (MT5 ${code})`:""}`;
  };
  [["buy",Boolean(s.buy_entry_eligible),s.buy_block_reason],["sell",Boolean(s.sell_entry_eligible),s.sell_block_reason]].forEach(([side,ready,reason])=>{
    const el=document.getElementById(`signal-${side}-state`);
    el.textContent=ready?"READY":"BLOCKED"; el.className="badge "+(ready?"ok":"bad");
    const adjusted=side==="buy"?buyAdj:sellAdj;
    const penaltyNote=adjusted<0?` · post-penalty score ${adjusted.toFixed(2)}, executable floor 0.00`:"";
    document.getElementById(`signal-${side}-reason`).textContent=orderReason(side,reason)+penaltyNote;
  });

  let block=String(s.last_global_block_reason||"NONE").toUpperCase();
  const capital=state.zonePlan?.capital_sizing||{};
  const capitalHardVeto=capital.veto_new_risk===true || s.capital_veto_new_risk===true;
  const recoveryProbe=String(capital.loss_protection?.state||"").toUpperCase()==="RECOVERY_PROBE";
  if(s.terminal_algo_trading_allowed===false)block="MT5_ALGO_TRADING_DISABLED";
  else if(s.ea_trading_allowed===false)block="EA_LIVE_TRADING_DISABLED";
  else if(s.account_trade_allowed===false||s.account_expert_trading_allowed===false)block="ACCOUNT_ALGO_TRADING_DISABLED";
  else if(capitalHardVeto)block="ATLAS_CAPITAL_RISK_VETO";
  const clear=block==="NONE"||block==="CLEAR";
  const executionIssue=[s.buy_block_reason,s.sell_block_reason].some(r=>/ORDER_(SEND_ERROR|REJECTED|PREFLIGHT_REJECTED)|LOCAL_STOP_PREFLIGHT|FINAL_FRESH_QUOTE_PREFLIGHT|POST_FILL_PROTECTION/.test(String(r||""))) || /FAILED|EMERGENCY_CLOSE/.test(String(s.preflight_protection_state||""));
  const g=document.getElementById("signal-global-status");
  const brainReview=String(capital.loss_protection?.state||"").toUpperCase()==="BRAIN_REVIEW_PENDING";
  g.textContent=brainReview?"BRAIN REVIEW IN FLIGHT":capitalHardVeto?"CAPITAL RISK GATE ACTIVE":recoveryProbe?"LEGACY RECOVERY PROBE ARMED":executionIssue?"BROKER EXECUTION BLOCKED":clear?"ENTRY SYSTEM CLEAR":"ENTRY SYSTEM BLOCKED";
  g.className="badge "+(brainReview?"warn":capitalHardVeto?"bad":recoveryProbe?"warn":executionIssue?"bad":clear?"ok":"bad");
  document.getElementById("signal-global-block").textContent=pretty(block);
  document.getElementById("signal-newbar").textContent=s.new_bar_entry_only?(s.new_bar_ready?"READY":"WAITING"):"INTRABAR";
  document.getElementById("signal-cooldown").textContent=s.cooldown_active?"ACTIVE":"INACTIVE";
  document.getElementById("signal-spread").textContent=s.scalp_cost_ratio_feasible===false?"BLOCKED":s.scalp_cost_ratio_feasible===true?"CLEAR":"—";
}

function renderZoneChart(zoneMap,livePrice=null){
  const svg=document.getElementById("an-zone-chart");if(!svg)return;
  const bars=Array.isArray(zoneMap?.chart?.bars)?zoneMap.chart.bars:[];
  if(!bars.length){
    svg.innerHTML=`<rect width="1200" height="520" fill="rgba(5,9,16,.25)"/><text x="600" y="250" text-anchor="middle" fill="#94a3b8" font-size="18">Waiting for validated M30 candles and a detected zone map</text><text x="600" y="280" text-anchor="middle" fill="#64748b" font-size="13">Atlas will render closed candles and prioritized multi-timeframe zones here.</text>`;
    return;
  }

  const width=1200,height=520,margin={left:20,right:150,top:20,bottom:44};
  const plotWidth=width-margin.left-margin.right,plotHeight=height-margin.top-margin.bottom;
  const barLow=Math.min(...bars.map(bar=>Number(bar.low)));
  const barHigh=Math.max(...bars.map(bar=>Number(bar.high)));
  const baseRange=Math.max(barHigh-barLow,Math.abs(barHigh)*0.001,1);
  const allZones=Array.isArray(zoneMap.zones)?zoneMap.zones:[];
  const current=Number(livePrice||zoneMap.current_price||bars[bars.length-1].close);
  const distance=zone=>current<Number(zone.low)?Number(zone.low)-current:current>Number(zone.high)?current-Number(zone.high):0;
  const nearby=allZones.filter(zone=>Number(zone.high)>=barLow-baseRange*.35&&Number(zone.low)<=barHigh+baseRange*.35);
  let visibleZones=["DEMAND","SUPPLY"].flatMap(side=>nearby.filter(zone=>zone.side===side).sort((a,b)=>distance(a)-distance(b)||Number(b.score)-Number(a.score)).slice(0,2));
  [zoneMap.nearest_demand,zoneMap.nearest_supply].filter(Boolean).forEach(zone=>{if(!visibleZones.some(item=>item.zone_id===zone.zone_id))visibleZones.push(zone)});
  visibleZones=visibleZones.sort((a,b)=>distance(a)-distance(b)||Number(b.score)-Number(a.score)).slice(0,4);
  const rawMin=Math.min(barLow,...visibleZones.map(zone=>Number(zone.low)));
  const rawMax=Math.max(barHigh,...visibleZones.map(zone=>Number(zone.high)));
  const scaleRange=Math.max(rawMax-rawMin,1),priceMin=rawMin-scaleRange*.055,priceMax=rawMax+scaleRange*.055;
  const y=price=>margin.top+(priceMax-Number(price))/(priceMax-priceMin)*plotHeight;
  const step=plotWidth/bars.length,candleWidth=Math.max(2,Math.min(9,step*.62));
  const parts=[`<rect x="0" y="0" width="${width}" height="${height}" fill="rgba(5,9,16,.22)"/>`];

  for(let index=0;index<=6;index++){
    const price=priceMax-(priceMax-priceMin)*index/6,py=y(price);
    parts.push(`<line x1="${margin.left}" y1="${py}" x2="${margin.left+plotWidth}" y2="${py}" stroke="rgba(148,163,184,.13)" stroke-width="1"/>`);
    parts.push(`<text x="${margin.left+plotWidth+10}" y="${py+4}" fill="#7f8da3" font-size="11">${fmt(price,2)}</text>`);
  }

  const zoneVisuals=[];
  visibleZones.forEach(zone=>{
    const highY=y(zone.high),lowY=y(zone.low),zoneHeight=Math.max(3,lowY-highY);
    const demand=zone.side==="DEMAND",fill=demand?"rgba(74,222,128,.14)":"rgba(251,113,133,.13)",stroke=demand?"rgba(74,222,128,.62)":"rgba(251,113,133,.62)";
    const label=`${zone.side} · ${zone.timeframe} ${pretty(zone.kind)} · ${fmt(zone.low,2)}–${fmt(zone.high,2)}`;
    zoneVisuals.push({zone,highY,lowY,demand,stroke,label,desiredY:(highY+lowY)/2});
    parts.push(`<g><title>${esc(label)} · score ${fmt(zone.score,1)}</title><rect x="${margin.left}" y="${highY}" width="${plotWidth}" height="${zoneHeight}" fill="${fill}" stroke="${stroke}" stroke-width="1" stroke-dasharray="5 4"/></g>`);
  });

  bars.forEach((bar,index)=>{
    const x=margin.left+step*(index+.5),openY=y(bar.open),closeY=y(bar.close),highY=y(bar.high),lowY=y(bar.low);
    const bullish=Number(bar.close)>=Number(bar.open),color=bullish?"#4ade80":"#fb7185";
    parts.push(`<line x1="${x}" y1="${highY}" x2="${x}" y2="${lowY}" stroke="${color}" stroke-width="1" opacity=".88"/>`);
    parts.push(`<rect x="${x-candleWidth/2}" y="${Math.min(openY,closeY)}" width="${candleWidth}" height="${Math.max(1.5,Math.abs(closeY-openY))}" fill="${color}" opacity=".94"/>`);
  });

  let lastLabelY=margin.top+5;
  zoneVisuals.sort((a,b)=>a.desiredY-b.desiredY).forEach(item=>{
    const labelY=Math.min(margin.top+plotHeight-4,Math.max(item.desiredY,lastLabelY+18));
    lastLabelY=labelY;
    const shortKind=item.zone.kind==="ORDER_BLOCK"?"OB":item.zone.kind==="SUPPORT_RESISTANCE"?"S/R":"FVG";
    const shortLabel=`${item.zone.timeframe} ${shortKind} · ${item.zone.side}`;
    parts.push(`<line x1="${margin.left+205}" y1="${labelY-4}" x2="${margin.left+222}" y2="${item.desiredY}" stroke="${item.stroke}" stroke-width="1" opacity=".7"/>`);
    parts.push(`<rect x="${margin.left+4}" y="${labelY-15}" width="202" height="17" rx="4" fill="rgba(5,9,16,.78)" stroke="${item.stroke}" stroke-width=".6"/>`);
    parts.push(`<text x="${margin.left+10}" y="${labelY-4}" fill="${item.demand?"#86efac":"#fda4af"}" font-size="9" font-weight="700">${esc(shortLabel)}</text>`);
  });

  const currentY=y(current);
  parts.push(`<line x1="${margin.left}" y1="${currentY}" x2="${margin.left+plotWidth}" y2="${currentY}" stroke="#60a5fa" stroke-width="1.4" stroke-dasharray="7 5"/>`);
  parts.push(`<rect x="${margin.left+plotWidth+5}" y="${currentY-11}" width="106" height="22" rx="5" fill="#2563eb"/><text x="${margin.left+plotWidth+12}" y="${currentY+4}" fill="white" font-size="11" font-weight="700">${fmt(current,3)}</text>`);
  parts.push(`<text x="${margin.left+8}" y="${margin.top+17}" fill="#dbeafe" font-size="13" font-weight="700">${esc(text(zoneMap.symbol))} · M30 · ${esc(pretty(zoneMap.composite_bias))} STRUCTURE</text>`);

  [0,Math.floor((bars.length-1)/4),Math.floor((bars.length-1)/2),Math.floor((bars.length-1)*3/4),bars.length-1].forEach((index,labelIndex)=>{
    const x=margin.left+step*(index+.5),date=new Date(Number(bars[index].time_epoch)*1000);
    const label=date.toLocaleString([],{month:"short",day:"numeric",hour:"2-digit",minute:"2-digit"});
    const anchor=labelIndex===0?"start":labelIndex===4?"end":"middle";
    parts.push(`<text x="${x}" y="${height-14}" text-anchor="${anchor}" fill="#7f8da3" font-size="10">${esc(label)}</text>`);
  });
  const hidden=Math.max(0,allZones.length-visibleZones.length);
  if(hidden)parts.push(`<text x="${margin.left+plotWidth-4}" y="${margin.top+17}" text-anchor="end" fill="#94a3b8" font-size="10">${hidden} farther zone${hidden===1?"":"s"} listed below</text>`);
  svg.innerHTML=parts.join("");
}

function renderAnalysis(){
  const s=state.status||{}, i=state.intelligence||{}, p=state.proposal||{}, r=state.responsiveness||{};
  const regime=i.regime||{}, risk=i.risk||i.risk_governor||{};
  const direction=String(regime.direction||"NEUTRAL").toUpperCase();
  const bias=direction.includes("BULL")?"BULLISH":direction.includes("BEAR")?"BEARISH":"NEUTRAL";
  document.getElementById("an-bias").textContent=bias;
  document.getElementById("an-bias").className="value small "+(bias==="BULLISH"?"pos":bias==="BEARISH"?"neg":"");
  document.getElementById("an-regime").textContent=pretty(regime.regime||"UNKNOWN");
  document.getElementById("an-volatility").textContent=pretty(regime.volatility||"UNKNOWN");
  document.getElementById("an-vol-ratio").textContent=`Ratio ${fmt(s.volatility_ratio,2)} · ATR ${fmt(s.current_atr,3)}`;
  document.getElementById("an-fit").textContent=pretty(i.fit||"UNKNOWN");
  document.getElementById("an-confidence").textContent=i.confidence==null?"Confidence —":`Confidence ${fmt(i.confidence,1)}%`;
  document.getElementById("an-risk").textContent=pretty(risk.state||currentRisk());
  document.getElementById("an-responsiveness").textContent=`Responsiveness ${text(r.profile)}`;
  document.getElementById("an-thesis").textContent=i.summary||"Atlas has not produced a current market thesis.";
  const reasons=[...(regime.reasons||[]),...(i.recommendations||[]),...(i.cautions||[])].slice(0,8);
  document.getElementById("an-reasons").innerHTML=reasons.map((x,index)=>`<div class="analysis-item ${index<2?"info":""}">${esc(text(typeof x==="string"?x:x?.message||x?.reason||JSON.stringify(x)))}</div>`).join("")||`<div class="analysis-item">No supporting reasons returned yet.</div>`;

  const spreadPrice=Math.abs(Number(s.ask||0)-Number(s.bid||0));
  const spreadPoints=Number(s.spread_points||0);
  const point=Number(s.symbol_point||((spreadPrice>0&&spreadPoints>0)?spreadPrice/spreadPoints:0));
  const spreadCapPoints=Number(s.effective_spread_cap_points||0);
  const spreadCapPrice=spreadCapPoints>0&&point>0?spreadCapPoints*point:0;
  const costRatio=spreadCapPrice>0?spreadPrice/spreadCapPrice:null;
  const gateBasis=text(s.scalp_cost_gate_basis,"UNKNOWN");
  const costLimiter=text(s.scalp_cost_limiting_factor,"NONE");
  const costAdjusted=Boolean(s.scalp_cost_adjusted);
  const costFeasible=s.scalp_cost_feasible!==false;
  const baseStopPoints=Number(s.scalp_base_stop_points||0);
  const baseTargetPoints=Number(s.scalp_base_target_points||0);
  const plannedStopPoints=Number(s.scalp_planned_stop_points||0);
  const plannedTargetPoints=Number(s.scalp_planned_target_points||0);
  const baseStop=baseStopPoints>0&&point>0?baseStopPoints*point:null;
  const baseTarget=baseTargetPoints>0&&point>0?baseTargetPoints*point:null;
  const plannedStop=plannedStopPoints>0&&point>0?plannedStopPoints*point:null;
  const plannedTarget=plannedTargetPoints>0&&point>0?plannedTargetPoints*point:null;
  const spreadToStop=Number(s.scalp_spread_to_stop_ratio||0);
  const spreadToTarget=Number(s.scalp_spread_to_target_ratio||0);
  const maxStopRatio=Number(s.scalp_max_spread_stop_ratio||0.20);
  const maxTargetRatio=Number(s.scalp_max_spread_target_ratio||0.15);
  const costRatioFeasible=s.scalp_cost_ratio_feasible!==false;
  const structureFeasible=s.scalp_structure_feasible!==false;
  const structureReason=text(s.scalp_structure_reason,"UNKNOWN");
  const stopExpansion=Number(s.scalp_stop_expansion_ratio||1);
  const targetExpansion=Number(s.scalp_target_expansion_ratio||1);
  const stopAtrRatio=Number(s.scalp_planned_stop_atr_ratio||0);
  const spreadAtrRatio=Number(s.scalp_spread_atr_ratio||0);
  const maxExpansion=Number(s.scalp_max_stop_expansion_ratio||0);
  const maxStopAtr=Number(s.scalp_max_stop_atr_ratio||0);
  const maxSpreadAtr=Number(s.scalp_max_spread_atr_ratio||0);
  let costState="INSUFFICIENT DATA", costClass="warn", costNote="Nyao needs a valid economic spread cap before judging scalp transaction cost.";
  if(costRatio!==null){
    if(costRatioFeasible && !structureFeasible){
      costState="STRUCTURE MISMATCH";costClass="bad";
      costNote=`Transaction-cost ratios can be made viable, but doing so would distort the scalp beyond its market-structure envelope (${pretty(structureReason)}). Stop expansion ${fmt(stopExpansion,1)}× / max ${fmt(maxExpansion,1)}× · planned stop ${fmt(stopAtrRatio,1)} ATR / max ${fmt(maxStopAtr,1)} · spread ${fmt(spreadAtrRatio,1)} ATR / max ${fmt(maxSpreadAtr,1)}. Atlas waits for a larger genuine market opportunity rather than manufacturing a huge stop around the spread.`;
    }else if(!costFeasible || !costRatioFeasible || costRatio>1){
      costState="COST BLOCKED";costClass="bad";
      costNote=`Spread ${fmt(spreadPrice,3)} cannot be supported by the current scalp economics. ${plannedStop!=null?`Planned stop ${fmt(plannedStop,3)} (${fmt(spreadToStop*100,1)}% spread/stop; max ${fmt(maxStopRatio*100,0)}%) and target ${fmt(plannedTarget,3)} (${fmt(spreadToTarget*100,1)}% spread/target; max ${fmt(maxTargetRatio*100,0)}%). `:""}Basis ${pretty(gateBasis)} · limiter ${pretty(costLimiter)}.`;
    }else if(costRatio>=0.8){
      costState="COST NEAR LIMIT";costClass="warn";
      costNote=`Spread is ${fmt(costRatio*100,1)}% of the allowed economic cap. The trade can pass cost preflight, but there is little cost headroom.`;
    }else{
      costState=costAdjusted?"COST-ADAPTED VIABLE":"COST VIABLE";costClass="ok";
      costNote=`Spread uses ${fmt(costRatio*100,1)}% of the economic cap. ${costAdjusted&&baseStop!=null?`Nyao adapted stop ${fmt(baseStop,3)} → ${fmt(plannedStop,3)} and target ${fmt(baseTarget,3)} → ${fmt(plannedTarget,3)} before capital sizing. `:""}${plannedStop!=null?`Spread/stop ${fmt(spreadToStop*100,1)}% and spread/target ${fmt(spreadToTarget*100,1)}%. `:""}Structure ${fmt(stopExpansion,1)}× base stop · ${fmt(stopAtrRatio,1)} ATR stop · ${fmt(spreadAtrRatio,1)} ATR spread. Limiter ${pretty(costLimiter)}. Final preflight rechecks market structure, executable geometry and Atlas risk budget immediately before OrderSend.`;
    }
  }
  const costBadge=document.getElementById("an-cost-badge");costBadge.textContent=costState;costBadge.className="badge "+costClass;
  document.getElementById("an-spread-price").textContent=spreadPrice?fmt(spreadPrice,3):"—";
  document.getElementById("an-atr").textContent=spreadCapPrice?fmt(spreadCapPrice,3):"—";
  document.getElementById("an-spread-atr").textContent=costRatio===null?"—":`${fmt(costRatio,2)}×`;
  document.getElementById("an-eligible").textContent=r.entry_observations?.eligible_rate_pct==null?"—":`${fmt(r.entry_observations.eligible_rate_pct,1)}%`;
  document.getElementById("an-cost-note").textContent=costNote;

  const candles=state.candles||{}, candleReady=Boolean(candles.ready_for_zone_analysis);
  const zoneMap=state.zoneMap||{}, zonesDetected=zoneMap.state==="DETECTED_NOT_ACTIVATED";
  const zonePlan=state.zonePlan||{}, activePlan=zonePlan.zone_plan||null;
  const capital=zonePlan.capital_sizing||{};
  const liveBid=Number(s.bid),liveAsk=Number(s.ask);
  const liveChartPrice=liveBid>0?liveBid:liveAsk>0?liveAsk:Number(zoneMap.current_price||0);
  const zoneExecutorInstalled=Boolean(s.zone_execution_supported),zoneExecutorEnabled=Boolean(s.zone_execution_enabled);
  const analysisZoneAwarePlanned=Boolean(zonePlan?.zone_aware_scalping_active);
  const analysisZoneAware=Boolean(
    s.zone_aware_scalping_active ||
    (
      s.zone_directive_fresh!==false &&
      !s.zone_scalp_suspended &&
      ["ZONE_AWARE_SCALP","ZONE_CAPITAL_INFEASIBLE"].includes(String(s.zone_directive_state||"").toUpperCase())
    )
  );
  const analysisZoneOwnership=zoneOwnershipState(s);
  const zoneModeLive=Boolean(analysisZoneOwnership.owns&&!analysisZoneAware);
  const zoneNewEntryAuthority=Boolean(s.zone_mode_active&&!analysisZoneAware);
  const candleState=text(candles.state,"WAITING_FOR_NYAO_EXPORT");
  const zoneBadge=document.getElementById("an-zone-status");
  zoneBadge.textContent=zonesDetected?"ZONE MAP DETECTED":candleReady?"CANDLES VALIDATED":pretty(candleState);
  zoneBadge.className="badge "+(zonesDetected||candleReady?"ok":candleState==="INVALID"?"bad":"warn");
  const stageCandles=document.getElementById("an-stage-candles");
  stageCandles.textContent=candleReady?"READY":candleState==="INVALID"?"INVALID":"WAITING";
  stageCandles.className="value small "+(candleReady?"pos":candleState==="INVALID"?"neg":"");
  const stageZone=document.getElementById("an-stage-zone-engine");
  stageZone.textContent=zonesDetected?"READY":candleReady?"NEXT":"PENDING";
  stageZone.className="value small "+(zonesDetected?"pos":candleReady?"":"muted");
  document.getElementById("an-zone-title").textContent=zonesDetected
    ? `${text(zoneMap.symbol)} deterministic daily zone map`
    : candleReady
      ? "Candle foundation ready; no approved zone map yet"
    : "No approved internal zone map yet";
  const candleMessages=[...(candles.blockers||[]),...(candles.warnings||[])];
  document.getElementById("an-candle-detail").textContent=zonesDetected
    ? `${text(zoneMap.zone_count,0)} active zones · ${text(zoneMap.invalidated_zone_count,0)} invalidated archived · ${pretty(zoneMap.composite_bias)} composite structure · map ${text(zoneMap.map_id)}. ${zoneModeLive?`${pretty(s.zone_side||"ZONE")} zone execution is currently active in Nyao.`:"The map is available; execution authority activates only when a qualified zone campaign is live."}`
    : candleReady
      ? `Validated closed M30/H1/H4 history for ${text(candles.symbol)}. Export age ${age(candles.export_age_seconds)}. The deterministic zone engine is now the next authority layer.`
    : candleMessages[0]||"Atlas is waiting for Nyao's validated, closed-bar multi-timeframe export. It will not invent price zones from live ticks alone.";
  document.getElementById("an-zone-stats").innerHTML=zonesDetected?[
    ["Map version",zoneMap.map_id],
    ["Live MT5 bid",liveBid>0?fmt(liveBid,3):"—"],
    ["Live MT5 ask",liveAsk>0?fmt(liveAsk,3):"—"],
    ["Closed M30 reference",fmt(zoneMap.current_price,3)]
  ].map(([label,value],index)=>`<div class="kpi"><div class="label">${esc(label)}</div><div class="value small ${index===3?"neg":""}">${esc(text(value))}</div></div>`).join(""):"";
  const zoneRows=Array.isArray(zoneMap.zones)?zoneMap.zones:[];
  const gateStage=document.getElementById("an-stage-zone-gate");
  gateStage.textContent=zoneModeLive?"ZONE MODE LIVE":zoneExecutorInstalled&&zoneExecutorEnabled?"READY":zoneExecutorInstalled?"DISABLED":"INSTALL BUILD";
  gateStage.className="value small "+(zoneModeLive||zoneExecutorInstalled&&zoneExecutorEnabled?"pos":zoneExecutorInstalled?"neg":"muted");
  const zoneExecution=document.getElementById("an-zone-execution");
  if(activePlan){
    const entries=Array.isArray(activePlan.entries)?activePlan.entries:[], targets=Array.isArray(activePlan.take_profits)?activePlan.take_profits:[],zc=activePlan.confirmation?.zone_confirmation||{};
    const quoteLabel=zonePlan.price_basis==="BID_SELL_EXECUTION"?"live bid":zonePlan.price_basis==="ASK_BUY_EXECUTION"?"live ask":pretty(zonePlan.price_basis||"execution quote");
  const zoneSpread=activePlan.confirmation?.spread_assessment||{};
  const sourceInvalidated=Boolean(zonePlan.source_zone_invalidated||zonePlan.campaign_lock?.source_zone_invalidated);
  const zoneLifecycleLabel=sourceInvalidated?"INVALIDATED · MANAGEMENT ONLY":(zonePlan.zone_aware_scalping_active?"ZONE-AWARE SCALP":"ZONE CAMPAIGN");
  zoneExecution.innerHTML=`<div class="zone-plan ${sourceInvalidated?"invalidated":""}"><div class="zone-plan-head"><div><div class="label">ATLAS MODE DIRECTIVE · ${esc(text(activePlan.plan_id))}</div><div class="zone-price" style="margin-top:5px">${esc(activePlan.side)} ${esc(zoneLifecycleLabel)} · ${sourceInvalidated?"source thesis failed; new campaign layers disabled while existing exposure remains managed":zonePlan.zone_aware_scalping_active?"zone context retained; ordinary scalp engine released":"ordinary scalping suspended"}</div><div class="muted" style="margin-top:5px">${esc(quoteLabel)} ${fmt(zonePlan.live_price,3)} is inside ${esc(activePlan.source_zone?.timeframe||"")} ${esc(pretty(activePlan.source_zone?.kind||"ZONE"))}. MT5 bid ${fmt(zonePlan.live_bid,3)} · ask ${fmt(zonePlan.live_ask,3)} · closed M30 reference ${fmt(zonePlan.closed_m30_reference,3)}. Zone spread ${fmt(zoneSpread.spread_price,3)} / adaptive cap ${fmt(zoneSpread.effective_cap_price,3)}${zoneSpread.limiting_factor?` · ${esc(pretty(zoneSpread.limiting_factor))} limited`:""}; scalp cost gate is separate. ${zoneExecutorInstalled?`Nyao executor: ${esc(pretty(s.zone_last_execution_reason||"READY"))}.`:"Install the newly compiled Nyao build to enforce this directive."}</div></div><span class="badge ${sourceInvalidated?"bad":zoneModeLive?"ok":"warn"}">${esc(sourceInvalidated?"ZONE INVALIDATED":zoneModeLive?"LIVE IN NYAO":pretty(zonePlan.state))}</span></div><div class="zone-plan-grid">${entries.map((entry,index)=>`<div class="zone-plan-leg"><div class="label">ENTRY ${entry.leg} · ${fmt(entry.risk_allocation_pct,0)}% · ${esc(pretty(entry.order_type))}</div><strong>${entry.order_type==="MARKET_ON_CONFIRMATION"?`LIVE (ref ${fmt(entry.entry_price,3)})`:fmt(entry.entry_price,3)}</strong><div class="muted">${targets[index]?`TP${targets[index].target} ${fmt(targets[index].price,3)} · close ${fmt(targets[index].close_allocation_pct,0)}%`:"Target pending"}</div></div>`).join("")}</div><div class="grid g4" style="margin-top:9px"><div class="kpi"><div class="label">Shared stop</div><div class="value small neg">${fmt(activePlan.stop_loss,3)}</div></div><div class="kpi"><div class="label">Total account risk</div><div class="value small">${fmt(activePlan.risk?.account_risk_pct,2)}%</div></div><div class="kpi"><div class="label">Zone confirmation</div><div class="value small ${zc.eligible?"pos":""}">${fmt(zc.combined_score,1)} / ${fmt(zc.threshold,1)}</div><div class="muted">Directional ${fmt(zc.directional_score,2)} / ${fmt(zc.minimum_directional_score,2)} · policy ${text(zc.policy_epoch)}</div></div><div class="kpi"><div class="label">Execution authority</div><div class="value small ${zoneModeLive?"pos":"neg"}">${zoneModeLive?"ACTIVE":"NOT ACTIVE"}</div></div></div>${(zonePlan.blockers||[]).length?`<div class="callout" style="margin-top:9px">${esc(zonePlan.blockers.join(" "))}</div>`:""}</div>`;
  }else{
    const sizingNote=capital.version?` Atlas capital budget: ${fmt(capital.approved_scalp_risk_pct,3)}% equity per qualified scalp (${esc(pretty(capital.decision))}); current-account loss streak ${text(capital.consecutive_losses,0)}.`:"";
    zoneExecution.innerHTML=`<div class="zone-plan"><div class="zone-plan-head"><div><div class="label">ATLAS MODE DIRECTIVE</div><div class="zone-price" style="margin-top:5px">${esc(pretty(zonePlan.mode||"WAITING"))}</div><div class="muted" style="margin-top:5px">${zonePlan.mode==="SCALP_MODE"?"Live price is outside the priority zones, so the ordinary scalp strategy remains the proposed mode.":esc((zonePlan.blockers||[])[0]||"Waiting for the live zone execution plan.")}${sizingNote}</div></div><span class="badge ${capital.veto_new_risk?"bad":zonePlan.mode==="SCALP_MODE"?"info":"warn"}">${esc(capital.veto_new_risk?"CAPITAL VETO":pretty(zonePlan.state||"PENDING"))}</span></div></div>`;
  }
  const liveZoneRelation=zone=>{
    const decisionPrice=zone.side==="DEMAND"?(liveAsk>0?liveAsk:liveBid):(liveBid>0?liveBid:liveAsk);
    const relation=decisionPrice<Number(zone.low)?"BELOW":decisionPrice>Number(zone.high)?"ABOVE":"INSIDE";
    const basis=zone.side==="DEMAND"?"ASK":"BID";
    return {decisionPrice,relation,basis};
  };
  document.getElementById("an-zone-list").innerHTML=zoneRows.map(zone=>{const live=liveZoneRelation(zone);return `<div class="zone-card ${zone.side==="DEMAND"?"demand":"supply"}"><div><span class="badge ${zone.side==="DEMAND"?"ok":"bad"}">${esc(zone.side)}</span><div class="muted" style="margin-top:5px">${esc(zone.timeframe)} · ${esc(pretty(zone.kind))}</div></div><div><div class="zone-price">${fmt(zone.low,3)} – ${fmt(zone.high,3)}</div><div class="muted zone-evidence">${esc((zone.evidence||[])[0]||"Closed-candle structure zone")}</div></div><div><span class="badge ${live.relation==="INSIDE"?"ok":zone.status==="FRESH"?"info":"warn"}">LIVE ${esc(live.relation)}</span><div class="muted" style="margin-top:5px">${live.basis} ${fmt(live.decisionPrice,3)} · ${esc(text((zone.confluence||[]).length,0))} confluence</div></div><div class="zone-score"><strong>${fmt(zone.score,1)}</strong><div class="muted">score</div></div></div>`}).join("");
  const invalidatedRows=Array.isArray(zoneMap.invalidated_zones)?zoneMap.invalidated_zones:[];
  const lifecycleRoot=document.getElementById("an-zone-lifecycle");
  if(lifecycleRoot){
    const latestInvalid=invalidatedRows[0]||null;
    lifecycleRoot.innerHTML=zonesDetected
      ?`<strong>ZONE LIFECYCLE</strong> · ${text(zoneMap.zone_count,0)} active · ${text(zoneMap.invalidated_zone_count,0)} invalidated archived. <span class="muted">Invalidation requires a later closed candle beyond the technical boundary; wick-only penetration is retained as mitigation.</span>${latestInvalid?`<div style="margin-top:6px"><span class="badge bad">LATEST INVALIDATION</span> ${esc(latestInvalid.timeframe)} ${esc(pretty(latestInvalid.kind))} ${esc(latestInvalid.side)} · ${esc(latestInvalid.invalidation_reason||"")}</div>`:""}`
      :"Zone lifecycle is waiting for a validated deterministic map.";
  }
  const invalidatedCount=document.getElementById("an-invalidated-count");
  if(invalidatedCount){invalidatedCount.textContent=`${invalidatedRows.length} INVALIDATED`;invalidatedCount.className="badge "+(invalidatedRows.length?"bad":"info");}
  const invalidatedRoot=document.getElementById("an-invalidated-zone-list");
  if(invalidatedRoot){invalidatedRoot.innerHTML=invalidatedRows.length?invalidatedRows.map(zone=>`<div class="zone-card invalidated"><div><span class="badge bad">INVALIDATED</span><div class="muted" style="margin-top:5px">${esc(zone.timeframe)} · ${esc(pretty(zone.kind))} · ${esc(zone.side)}</div></div><div><div class="zone-price">${fmt(zone.low,3)} – ${fmt(zone.high,3)}</div><div class="muted zone-evidence">${esc(zone.invalidation_reason||"Closed candle invalidated the technical boundary.")}</div></div><div><span class="badge bad">${esc(pretty(zone.invalidation_rule||"CLOSED_CANDLE_BREAK"))}</span><div class="muted" style="margin-top:5px">Close ${fmt(zone.invalidating_close,3)} · boundary ${fmt(zone.invalidation_boundary,3)} · penetration ${fmt(zone.invalidation_penetration_atr,2)} ATR</div></div><div class="zone-score"><strong>${zone.invalidated_at_epoch?age(Math.max(0,Date.now()/1000-Number(zone.invalidated_at_epoch))):"—"}</strong><div class="muted">ago</div></div></div>`).join(""):`<div class="callout">No invalidated zones in the current validated candle history.</div>`;}
  const zoneScenarios=Array.isArray(zoneMap.scenarios)?zoneMap.scenarios:[];
  document.getElementById("an-zone-scenario-list").innerHTML=zoneScenarios.map(item=>`<div class="analysis-item ${item.side==="BUY"?"buy":"sell"}"><div class="row"><strong>${esc(item.side)} CLOSED-CANDLE MAP SCENARIO</strong><span class="badge warn">${esc(pretty(item.state))}</span></div><div class="muted" style="margin-top:5px">Closed M30 reference ${fmt(item.reference_price,3)} · ${item.zone_id?`${fmt(item.zone_low,3)} – ${fmt(item.zone_high,3)} · `:""}${esc((item.conditions||[])[0]||"No qualified zone available.")} Live authority is shown in the mode directive above.</div></div>`).join("");
  renderZoneChart(zoneMap,liveChartPrice);
  document.getElementById("an-mtf-grid").innerHTML=["M30","H1","H4"].map(tf=>{
    const item=candles.timeframes?.[tf]||{};
    const ready=item.state==="READY";
    return `<div class="kpi"><div class="row"><div class="label">${tf} closed bars</div><span class="badge ${ready?"ok":"warn"}">${esc(pretty(item.state||"WAITING"))}</span></div><div class="value small">${esc(text(item.bar_count,0))} / ${esc(text(item.minimum_bars,"—"))}</div><div class="muted">Latest ${item.latest_bar_age_seconds==null?"—":age(item.latest_bar_age_seconds)+" ago"}</div></div>`;
  }).join("");

  const scenarios=[
    {side:"BUY",ready:Boolean(s.buy_entry_eligible),score:Number(s.buy_adjusted_score||0),threshold:Number(s.buy_effective_threshold||0),reason:String(s.buy_block_reason||"NONE"),kind:"buy"},
    {side:"SELL",ready:Boolean(s.sell_entry_eligible),score:Number(s.sell_adjusted_score||0),threshold:Number(s.sell_effective_threshold||0),reason:String(s.sell_block_reason||"NONE"),kind:"sell"}
  ];
  const activeZoneSide=pretty(activePlan?.side||s.zone_side||"ZONE");
  const qualified=scenarios.filter(x=>x.ready);
  const strongestQualified=qualified.length?qualified.reduce((a,b)=>b.score>a.score?b:a):null;
  const lastOrderDirection=String(s.last_order_direction||"NONE").toUpperCase();
  const lastOrderRetcode=Number(s.last_order_retcode||0);
  document.getElementById("an-scenarios").innerHTML=scenarios.map(x=>{
    const counterDirection=analysisZoneAware&&activeZoneSide!=="ZONE"&&x.side!==activeZoneSide;
    const executionError=/ORDER_(SEND_ERROR|REJECTED|PREFLIGHT_REJECTED)|LOCAL_STOP_PREFLIGHT/.test(x.reason);
    const lostArbitration=!zoneModeLive&&!counterDirection&&x.ready&&strongestQualified&&strongestQualified.side!==x.side;
    let scalpState="WAIT";
    if(zoneModeLive) scalpState="ORDINARY SCALP SUSPENDED";
    else if(counterDirection) scalpState="ZONE-CONTEXT BLOCKED";
    else if(executionError) scalpState=x.reason.includes("PREFLIGHT")?"LOCAL PREFLIGHT BLOCKED":"BROKER / SEND REJECTED";
    else if(lostArbitration) scalpState="SIGNAL QUALIFIED · NOT SELECTED";
    else if(x.ready) scalpState="SIGNAL QUALIFIED · SELECTED";
    const authority=zoneModeLive?`ACTIVE · ${activeZoneSide} CAMPAIGN`:analysisZoneAware?`ZONE-AWARE SCALP · ${activeZoneSide} ALIGNED`:zoneExecutorInstalled&&zoneExecutorEnabled?"SCALP ACTIVE · ZONE ENGINE ARMED":"SCALP ACTIVE";
    let explanation="";
    if(zoneModeLive) explanation=`Active ${activeZoneSide} zone campaign owns execution authority; this ${x.side} score is informational and cannot launch an ordinary scalp.`;
    else if(counterDirection) explanation=`${x.side} is counter-zone to the active ${activeZoneSide} zone context; it requires the additional counter-zone evidence premium and may be blocked near campaign commitment.`;
    else if(executionError) explanation=`Execution did not complete: ${pretty(x.reason)}${lastOrderDirection===x.side&&lastOrderRetcode?` · MT5 ${lastOrderRetcode}`:""}. Nyao will re-evaluate on the next eligible cycle; it does not fall back into the opposite direction.`;
    else if(lostArbitration) explanation=`Signal passed its own threshold, but ${strongestQualified.side} won this cycle's directional arbitration (${fmt(strongestQualified.score,2)} vs ${fmt(x.score,2)}). No opposite-direction fallback is attempted if the selected side later fails execution.`;
    else if(x.ready) explanation=`Signal passed its threshold and won the currently qualified directional arbitration. Normal capital, spread, sizing, stop preflight and broker checks still apply before an order is accepted.`;
    else explanation=`Current blocker: ${pretty(text(x.reason,"NONE"))}`;
    const badgeClassName=executionError?"bad":lostArbitration?"info":zoneModeLive?"info":x.ready?"ok":"warn";
    return `<div class="analysis-item ${x.kind}"><div class="row"><strong>${x.side} · ${scalpState}</strong><span class="badge ${badgeClassName}">${fmt(x.score,2)} / ${fmt(x.threshold,2)}</span></div><div class="muted" style="margin-top:5px">${esc(explanation)} · Zone authority: ${esc(authority)}</div></div>`;
  }).join("");

  const bundle=p.llm_policy?.bundle||{}, critic=p.llm_policy?.critic||{};
  const criticBadge=document.getElementById("an-gemini-badge");criticBadge.textContent=text(critic.verdict,"NO LLM MAP");criticBadge.className="badge "+badgeClass(criticBadge.textContent);
  document.getElementById("an-gemini-thesis").textContent=bundle.policy_thesis||"No Gemini policy thesis is attached to the current analysis.";
  const llmEvidence=[...(bundle.performance_diagnosis||[]),...(bundle.responsiveness_diagnosis||[]),...(bundle.risks_and_tradeoffs||[])].slice(0,8);
  document.getElementById("an-gemini-evidence").innerHTML=llmEvidence.map(x=>`<div class="analysis-item info">${esc(x)}</div>`).join("")||`<div class="analysis-item">Run a Gemini policy cycle to populate this interpretation.</div>`;
}

function latestAckState(){
  const events=state.executionEvents?.events||[];
  const e=events.find(x=>String(x.action||"").startsWith("NYAO_ACK_"));
  return e?String(e.action).replace("NYAO_ACK_",""):"—";
}
function renderProposalChanges(id,changes){
  const root=document.getElementById(id);
  if(!root)return;
  const rows=Object.entries(changes||{});
  root.innerHTML=rows.length?rows.map(([k,v])=>`<div class="change"><strong>${esc(pretty(k))}</strong><span>${esc(text(v.current))}</span><span><span class="arrow">→</span> ${esc(text(v.shadow))}</span></div>`).join(""):`<div class="callout">No material runtime changes.</div>`;
}

function renderPortfolioRiskAllocation(){
  const capital=state.zonePlan?.capital_sizing||{},alloc=capital.portfolio_allocation||{},priority=capital.zone_priority_reservation||{};
  const operating=Math.max(0,Number(alloc.operating_risk_ceiling_amount||0)),active=Math.max(0,Number(alloc.reserved_active_risk_amount||0));
  const remainingBefore=Math.max(0,Number(priority.remaining_operating_before_priority??alloc.remaining_operating_risk_amount??Math.max(0,operating-active)));
  const zone=priority.active?Math.max(0,Math.min(remainingBefore,Number(priority.zone_priority_amount||0))):0,free=Math.max(0,remainingBefore-zone);
  const hard=Math.max(0,Number(alloc.portfolio_hard_ceiling_amount||0)),hardFree=Math.max(0,Number(alloc.remaining_hard_risk_amount||Math.max(0,hard-active)));
  const delta=operating-(active+zone+free),ok=Math.abs(delta)<=Math.max(.02,operating*.001);
  const badge=document.getElementById('portfolio-risk-badge');if(badge){badge.textContent=ok?'RECONCILED':'CHECK ALLOCATION';badge.className='badge '+(ok?'ok':'bad')}
  const set=(id,v)=>{const e=document.getElementById(id);if(e)e.textContent=v};set('portfolio-operating-ceiling',money(operating));set('portfolio-hard-ceiling',money(hard));set('portfolio-hard-headroom',`${money(hardFree)} hard headroom`);set('portfolio-risk-reconcile',ok?`${money(active)} active + ${money(zone)} zone priority + ${money(free)} free = ${money(operating)}`:`Allocation differs by ${money(delta)}.`);
  const bar=document.getElementById('portfolio-risk-bar');if(bar){const pct=x=>operating?Math.max(0,Math.min(100,x/operating*100)):0,segs=bar.querySelectorAll('.risk-segment');if(segs[0])segs[0].style.width=`${pct(active)}%`;if(segs[1])segs[1].style.width=`${pct(zone)}%`;if(segs[2])segs[2].style.width=`${pct(free)}%`}
  const cards=[];for(const r of (Array.isArray(alloc.reservations)?alloc.reservations:[])){const mtm=Number(r.current_mark_to_market||0);cards.push(`<div class="risk-allocation-card"><div class="risk-card-head"><div><span class="label">ACTIVE RESERVATION</span><strong>${esc(pretty(r.unit_type||'ACTIVE_RISK'))}</strong></div><span class="badge info">${esc(text(r.member_count,1))} MEMBER${Number(r.member_count||1)===1?'':'S'}</span></div><div class="risk-amount">${money(r.reserved_risk_amount||0)}</div><div class="risk-detail"><span>Unit</span><strong class="mono">${esc(text(r.unit_id,'—'))}</strong><span>Basis</span><strong>${esc(pretty(r.reservation_basis||'RESERVED'))}</strong><span>Current MTM</span><strong class="${mtm>0?'pos':mtm<0?'neg':''}">${money(mtm)}</strong></div></div>`)}
  if(zone>0){const plan=state.zonePlan?.zone_plan||{},side=String(state.zonePlan?.zone_aware_scalping_side||plan.side||state.status?.zone_side||'ZONE').toUpperCase();cards.push(`<div class="risk-allocation-card"><div class="risk-card-head"><div><span class="label">PROSPECTIVE RESERVATION</span><strong>${esc(side)} zone priority</strong></div><span class="badge warn">PRESERVED</span></div><div class="risk-amount">${money(zone)}</div><div class="risk-detail"><span>Basis</span><strong>${esc(pretty(priority.basis||'ZONE_PRIORITY'))}</strong><span>Plan</span><strong class="mono">${esc(text(plan.plan_id||state.status?.zone_plan_id||'—'))}</strong><span>Zone budget</span><strong>${money(capital.approved_zone_risk_amount||zone)}</strong></div></div>`)}
  cards.push(`<div class="risk-allocation-card"><div class="risk-card-head"><div><span class="label">FREE OPERATING RISK</span><strong>Fresh opportunity capacity</strong></div><span class="badge ${free>0?'ok':'bad'}">${free>0?'AVAILABLE':'FULLY ALLOCATED'}</span></div><div class="risk-amount">${money(free)}</div><div class="risk-detail"><span>Current scalp budget</span><strong>${money(capital.approved_scalp_risk_amount||0)}</strong><span>Remaining hard capacity</span><strong>${money(hardFree)}</strong><span>Operating utilization</span><strong>${operating?fmt((active+zone)/operating*100,1):'0.0'}%</strong></div></div>`);
  const root=document.getElementById('portfolio-risk-cards');if(root)root.innerHTML=cards.join('');
}

function renderPositions(){
  const s=state.status||{}, ps=Array.isArray(s.positions)?s.positions:[];
  const activePayload=state.outcomes?.active||{};
  const activeRows=Array.isArray(activePayload)
    ? activePayload
    : Object.values(activePayload||{});
  const lifecycleByTicket=new Map(
    activeRows.map(t=>[String(t.ticket),t])
  );

  document.getElementById("p-count").textContent=ps.length;
  document.getElementById("p-lots").textContent=fmt(s.total_lots,2);

  let activeRealized=0;
  let activeFloating=0;

  for(const p of ps){
    const life=lifecycleByTicket.get(String(p.ticket))||{};
    activeRealized+=Number(life.realized_net_pl||0);
    activeFloating+=Number(p.net_pl||0);
  }

  const realizedEl=document.getElementById("p-realized");
  realizedEl.textContent=money(activeRealized);
  realizedEl.className="value "+(activeRealized>0?"pos":activeRealized<0?"neg":"");

  const pl=s.strategy_floating_pl??s.floating_profit;
  const el=document.getElementById("p-pl");
  el.textContent=money(pl);
  el.className="value "+(Number(pl)>0?"pos":Number(pl)<0?"neg":"");

  const lifecycleTotal=activeRealized+Number(pl||0);
  const lifeEl=document.getElementById("p-lifecycle");
  lifeEl.textContent=money(lifecycleTotal);
  lifeEl.className="value "+(lifecycleTotal>0?"pos":lifecycleTotal<0?"neg":"");

  document.getElementById("p-chains").textContent=text(s.active_hedge_chains,0);
  renderPortfolioRiskAllocation();

  document.getElementById("positions-body").innerHTML=ps.length?ps.map(p=>{
    const life=lifecycleByTicket.get(String(p.ticket))||{};
    const floating=Number(p.net_pl||0);
    const realized=Number(life.realized_net_pl||0);
    const lifecycle=realized+floating;
    const initialVolume=Number(life.initial_volume??p.volume??0);
    const remaining=Number(p.volume||0);
    const closed=Number(life.closed_volume||Math.max(0,initialVolume-remaining));
    const volumeLabel=closed>0.0000001
      ? `${fmt(remaining,2)} / ${fmt(initialVolume,2)}`
      : fmt(remaining,2);
    const context=p.scalp_context_class&&p.scalp_context_class!=="NEUTRAL_SCALP"
      ? p.scalp_context_class
      : (p.order_origin||p.origin);
    return `<tr>
      <td class="mono">${esc(text(p.ticket))}</td>
      <td>${esc(text(p.type))}</td>
      <td title="${closed>0?`${fmt(closed,2)} lots already closed`:"Current open volume"}">${esc(volumeLabel)}</td>
      <td>${fmt(p.entry_price,3)}</td>
      <td>${fmt(p.current_price,3)}</td>
      <td class="${realized>0?"pos":realized<0?"neg":""}">${money(realized)}</td>
      <td class="${floating>0?"pos":floating<0?"neg":""}">${money(floating)}</td>
      <td class="${lifecycle>0?"pos":lifecycle<0?"neg":""}"><strong>${money(lifecycle)}</strong></td>
      <td class="neg">${fmt(p.sl,3)}</td>
      <td class="pos">${fmt(p.tp,3)}</td>
      <td>${esc(pretty(context))}${p.scalp_context_zone_side&&p.scalp_context_zone_side!=="NONE"?`<div class="muted">${esc(p.scalp_context_zone_side)} zone · pressure ${fmt(Number(p.scalp_context_pressure||0)*100,0)}%</div>`:""}</td>
      <td>${age(p.age_seconds)}</td>
    </tr>`}).join(""):`<tr><td colspan="12" class="muted">No strategy positions.</td></tr>`;

  renderClosedTrades();
  renderPerformance();
}

function renderClosedTrades(){
  const payload=state.outcomes||{};
  const closed=Array.isArray(payload.closed)?[...payload.closed]:[];
  closed.sort((a,b)=>Number(b.close_time_msc||b.close_time_epoch||0)-Number(a.close_time_msc||a.close_time_epoch||0));
  const root=document.getElementById("closed-trades-body");if(!root)return;
  const badge=document.getElementById("closed-trades-badge");
  const exact=closed.filter(t=>t.exact_realized_pl_available).length;
  badge.textContent=closed.length?`${closed.length} RECENT · ${exact} MT5 CONFIRMED`:"CURRENT ACCOUNT";
  badge.className="badge "+(exact?"ok":"info");
  root.innerHTML=closed.length?closed.slice(0,20).map(t=>{
    const initial=t.initial_position||{}, latest=t.latest_position||{};
    const pl=t.exact_realized_pl_available?Number(t.realized_net_pl||0):Number(t.final_observed_net_pl_before_disappearance||0);
    const closedAt=t.close_time_epoch?new Date(Number(t.close_time_epoch)*1000):t.disappeared_at?new Date(t.disappeared_at):null;
    const quality=t.exact_realized_pl_available?"MT5 CONFIRMED":pretty(t.outcome_quality||"INFERRED");
    return `<tr>
      <td class="mono">${esc(text(t.ticket||initial.ticket))}</td>
      <td>${esc(text(t.type||initial.type))}</td>
      <td>${fmt(t.initial_volume??initial.volume,2)}</td>
      <td>${fmt(t.entry_price??initial.entry_price,3)}</td>
      <td>${fmt(t.close_price??latest.current_price,3)}</td>
      <td class="${pl>0?"pos":pl<0?"neg":""}">${money(pl)}</td>
      <td>${esc(pretty(
  t.scalp_context_class&&t.scalp_context_class!=="NEUTRAL_SCALP"
    ? t.scalp_context_class
    : (t.order_origin||initial.order_origin||t.origin_guess)
))}</td>
      <td>${esc(text(t.entry_policy_epoch??initial.entry_policy_epoch,"—"))}</td>
      <td>${esc(pretty(t.trading_mode||"UNKNOWN"))}</td>
      <td>${closedAt&&!Number.isNaN(closedAt.getTime())?esc(closedAt.toLocaleString()):"—"}</td>
      <td><span class="badge ${t.exact_realized_pl_available?"ok":"warn"}">${esc(quality)}</span></td>
    </tr>`;
  }).join(""):`<tr><td colspan="11" class="muted">No closed trades recorded for the selected MT5 account yet.</td></tr>`;
}

function performanceUnitRow(label,row){
  row=row||{};const n=Number(row.closed_risk_units||0), net=Number(row.net_pl||0), exp=Number(row.expectancy||0), wr=Number(row.win_rate_pct||0);
  return `<div class="mini"><span class="label">Units</span><strong>${n}</strong></div><div class="mini"><span class="label">Net P/L</span><strong class="${net>0?"pos":net<0?"neg":""}">${money(net)}</strong></div><div class="mini"><span class="label">Expectancy</span><strong class="${exp>0?"pos":exp<0?"neg":""}">${money(exp)}</strong></div><div class="mini"><span class="label">Win rate</span><strong>${fmt(wr,1)}%</strong></div>`;
}
function median(values){const a=values.map(Number).filter(Number.isFinite).sort((x,y)=>x-y);if(!a.length)return null;const m=Math.floor(a.length/2);return a.length%2?a[m]:(a[m-1]+a[m])/2}
function renderPerformanceCurve(units){
  const root=document.getElementById("performance-equity-curve");if(!root)return;
  const ordered=[...units].sort((a,b)=>new Date(a.closed_at||0)-new Date(b.closed_at||0));if(!ordered.length){root.innerHTML='<div class="observability-empty">Equity curve will appear after completed risk units.</div>';return}
  let run=0;const vals=[0,...ordered.map(u=>(run+=Number(u.realized_net_pl||0)))];const lo=Math.min(...vals),hi=Math.max(...vals),span=Math.max(1,hi-lo),w=760,h=170,pad=18;
  const pts=vals.map((v,i)=>`${pad+(w-2*pad)*(i/Math.max(1,vals.length-1))},${pad+(h-2*pad)*(1-(v-lo)/span)}`).join(' ');
  const zeroY=pad+(h-2*pad)*(1-(0-lo)/span);
  root.innerHTML=`<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-label="Cumulative strategic realised P/L"><line x1="${pad}" y1="${zeroY}" x2="${w-pad}" y2="${zeroY}" stroke="rgba(142,160,184,.22)" stroke-width="1"/><polyline points="${pts}" fill="none" stroke="currentColor" stroke-width="2.5" vector-effect="non-scaling-stroke"/><text x="${pad}" y="15" fill="currentColor" font-size="10">${esc(money(hi))}</text><text x="${pad}" y="${h-5}" fill="currentColor" font-size="10">${esc(money(lo))}</text></svg>`;
}
function renderPerformance(){
  const p=state.performance||{},o=p.overall||{},risk=state.riskUnits||{};
  const allUnits=Array.isArray(risk.units)?risk.units:[], completed=allUnits.filter(u=>u.state==="COMPLETE");
  const byType=Object.fromEntries((p.by_risk_unit_type||[]).map(r=>[String(r.risk_unit_type||""),r]));
  const netEl=document.getElementById("perf-net");if(!netEl)return;
  netEl.textContent=money(o.net_pl);netEl.className="performance-net "+(Number(o.net_pl)>0?"pos":Number(o.net_pl)<0?"neg":"");
  document.getElementById("perf-count").textContent=text(o.closed_risk_units,0);
  const exp=document.getElementById("perf-expectancy");exp.textContent=money(o.expectancy);exp.className="value "+(Number(o.expectancy)>0?"pos":Number(o.expectancy)<0?"neg":"");
  document.getElementById("perf-win-rate").textContent=`${fmt(o.win_rate_pct,1)}%`;
  document.getElementById("perf-factor").textContent=o.profit_factor==null?"—":fmt(o.profit_factor,2);
  document.getElementById("perf-drawdown").textContent=money(o.maximum_closed_unit_drawdown);
  document.getElementById("perf-sample").textContent=`Sample ${pretty(o.sample_state||"INSUFFICIENT")}`;
  const quality=document.getElementById("perf-quality"), exact=Number(p.quality?.exact_realized_count||0), inferred=Number(p.quality?.inferred_count||0);
  quality.textContent=exact?"MT5 REALIZED":"INFERRED";quality.className="badge "+(exact&&inferred===0?"ok":exact?"info":"warn");
  document.getElementById("perf-data-quality").textContent=exact&&inferred===0?"AUTHORITATIVE":exact?"MIXED":"INFERRED";
  document.getElementById("perf-data-quality-copy").textContent=`${exact} exact · ${inferred} inferred risk units`;
  const headline=document.getElementById("performance-headline");
  headline.textContent=!Number(o.closed_risk_units)?"Atlas is collecting its first completed strategic outcomes.":Number(o.closed_risk_units)<20?"Early evidence only — useful for observation, not causal policy conclusions.":"Strategic performance evidence is accumulating; compare policy epochs and risk-unit types before adapting.";
  document.getElementById("performance-page-badge").textContent=`${text(state.selectedSymbol,"CURRENT")} · ${text(o.sample_state,"INSUFFICIENT")}`;
  renderPerformanceCurve(completed);

  const typeMap=[['STANDALONE_TRADE','perf-standalone','perf-standalone-badge'],['RECOVERY_CHAIN','perf-recovery','perf-recovery-badge'],['ZONE_CAMPAIGN','perf-zone','perf-zone-badge']];
  for(const [key,id,bid] of typeMap){const row=byType[key]||{};document.getElementById(id).innerHTML=performanceUnitRow(key,row);const b=document.getElementById(bid);b.textContent=text(row.sample_state,'NO DATA');b.className='badge '+(Number(row.closed_risk_units)>=20?'ok':Number(row.closed_risk_units)>0?'warn':'');}

  document.getElementById("perf-epochs").innerHTML=(p.by_policy_epoch||[]).slice(0,14).map(r=>`<tr><td>${esc(text(r.policy_epoch))}</td><td>${esc(text(r.closed_risk_units))}</td><td class="${Number(r.net_pl)>0?"pos":Number(r.net_pl)<0?"neg":""}">${money(r.net_pl)}</td><td>${money(r.expectancy)}</td><td>${fmt(r.win_rate_pct,1)}%</td><td><span class="badge ${Number(r.closed_risk_units)>=20?"ok":"warn"}">${esc(pretty(r.sample_state))}</span></td></tr>`).join("")||`<tr><td colspan="6" class="muted">No completed policy outcomes yet.</td></tr>`;
  document.getElementById("perf-modes").innerHTML=(p.by_trading_mode||[]).map(r=>`<tr><td>${esc(pretty(r.trading_mode))}</td><td>${esc(text(r.closed_risk_units))}</td><td class="${Number(r.net_pl)>0?"pos":Number(r.net_pl)<0?"neg":""}">${money(r.net_pl)}</td><td>${money(r.expectancy)}</td><td>${r.profit_factor==null?"—":fmt(r.profit_factor,2)}</td></tr>`).join("")||`<tr><td colspan="5" class="muted">No completed mode outcomes yet.</td></tr>`;

  const recent=[...completed].sort((a,b)=>new Date(b.closed_at||0)-new Date(a.closed_at||0)).slice(0,10);document.getElementById("perf-units-badge").textContent=`${completed.length} COMPLETE`;
  document.getElementById("perf-recent-units").innerHTML=recent.length?recent.map(u=>{const pl=Number(u.realized_net_pl||0);return `<div class="performance-result"><div><strong>${esc(pretty(u.unit_type))}</strong><div class="muted">${esc(text(u.unit_id))} · epoch ${esc(text(u.policy_epoch,'—'))}</div></div><strong class="${pl>0?'pos':pl<0?'neg':''}">${money(pl)}</strong><div class="muted">${u.closed_at?new Date(u.closed_at).toLocaleString():'—'}</div></div>`}).join(''):'<div class="observability-empty">No completed strategic risk units yet.</div>';

  const payload=state.outcomes||{}, tickets=Array.isArray(payload.closed)?payload.closed:[];const mfe=tickets.map(t=>t.max_favorable_net_pl_observed).filter(v=>Number.isFinite(Number(v))),mae=tickets.map(t=>t.max_adverse_net_pl_observed).filter(v=>Number.isFinite(Number(v)));const pls=tickets.map(t=>t.exact_realized_pl_available?Number(t.realized_net_pl||0):Number(t.final_observed_net_pl_before_disappearance||0)).filter(Number.isFinite);
  document.getElementById("perf-mfe").textContent=median(mfe)==null?'—':money(median(mfe));document.getElementById("perf-mae").textContent=median(mae)==null?'—':money(median(mae));document.getElementById("perf-ticket-average").textContent=pls.length?money(pls.reduce((a,b)=>a+b,0)/pls.length):'—';document.getElementById("perf-exact-tickets").textContent=`${tickets.filter(t=>t.exact_realized_pl_available).length} / ${tickets.length}`;
  const contextRoot=document.getElementById("perf-scalp-context");
  if(contextRoot){
    const ctx={};

    for(const t of tickets){
      const key=text(
        t.scalp_context_class || "NEUTRAL_SCALP"
      );

      const pl=t.exact_realized_pl_available
        ? Number(t.realized_net_pl||0)
        : Number(t.final_observed_net_pl_before_disappearance||0);

      if(!ctx[key])
        ctx[key]={n:0,w:0,pl:0};

      ctx[key].n++;

      if(Number.isFinite(pl)){
        ctx[key].pl+=pl;
        if(pl>0)ctx[key].w++;
      }
    }

    const rows=Object.entries(ctx)
      .sort((a,b)=>b[1].n-a[1].n);

    const maxN=Math.max(
      1,
      ...rows.map(x=>x[1].n)
    );

    contextRoot.innerHTML=rows.length
      ? rows.map(([k,v])=>`
        <div class="performance-bar">
          <span>${esc(pretty(k))}</span>
          <div class="performance-bar-track">
            <div class="performance-bar-fill"
              style="width:${Math.min(100,100*v.n/maxN)}%">
            </div>
          </div>
          <span class="${v.pl>0?'pos':v.pl<0?'neg':''}">
            ${v.n} · ${money(v.pl)} · ${fmt(100*v.w/Math.max(1,v.n),0)}% win
          </span>
        </div>
      `).join("")
      : '<div class="muted">No contextual scalp outcomes yet.</div>';
  }

  const reg={};for(const t of tickets){const key=text(t.entry_context?.regime,'UNKNOWN');const pl=t.exact_realized_pl_available?Number(t.realized_net_pl||0):Number(t.final_observed_net_pl_before_disappearance||0);if(!reg[key])reg[key]={n:0,pl:0};reg[key].n++;reg[key].pl+=Number.isFinite(pl)?pl:0}const rr=Object.entries(reg).sort((a,b)=>b[1].n-a[1].n),maxN=Math.max(1,...rr.map(x=>x[1].n));document.getElementById("perf-regimes").innerHTML=rr.length?rr.map(([k,v])=>`<div class="performance-bar"><span>${esc(pretty(k))}</span><div class="performance-bar-track"><div class="performance-bar-fill" style="width:${100*v.n/maxN}%"></div></div><span class="${v.pl>0?'pos':v.pl<0?'neg':''}">${v.n} · ${money(v.pl)}</span></div>`).join(''):'<div class="muted">No entry-context evidence yet.</div>';
  document.getElementById("perf-exact-units").textContent=exact;document.getElementById("perf-inferred-units").textContent=inferred;document.getElementById("perf-active-units").textContent=text(p.active_risk_unit_count??risk.active_unit_count,0);document.getElementById("perf-loss-streak").textContent=text(p.consecutive_completed_loss_units??risk.consecutive_completed_loss_units,0);
  const lb=document.getElementById("perf-learning-badge");lb.textContent=pretty(o.sample_state||'INSUFFICIENT');lb.className='badge '+(Number(o.closed_risk_units)>=100?'ok':Number(o.closed_risk_units)>=20?'info':'warn');document.getElementById("perf-note").textContent=p.interpretation||"Strategic performance requires completed risk units; small samples are preliminary and not causal proof.";
}
function renderLlmCycle(){
  const c=state.llmCycle||{};
  const models=state.llmStatus?.model_chain||[];
  const status=c.running?"REASONING":c.enabled?"EVENT DRIVEN":"EVENT DRIVEN";
  const badge=document.getElementById("cycle-badge");if(!badge)return;
  badge.textContent=status;badge.className="badge "+(c.running?"info":"ok");
  document.getElementById("cycle-last").textContent=c.last_completed_at?new Date(c.last_completed_at).toLocaleString():"Never";
  const seconds=Number(c.seconds_until_next_run);
  document.getElementById("cycle-next").textContent=c.running?"Reasoning now":c.enabled&&Number.isFinite(seconds)?age(seconds):"Disabled";
  document.getElementById("cycle-count").textContent=text(c.run_count,0);
  document.getElementById("cycle-critic").textContent=text(c.last_critic_verdict);
  const interval=document.getElementById("cycle-interval");
  if(interval && document.activeElement!==interval)interval.value=text(c.interval_minutes,240);
  const enabled=document.getElementById("cycle-enabled");
  if(enabled && document.activeElement!==enabled)enabled.checked=Boolean(c.enabled);
  const dwell=document.getElementById("cycle-dwell");if(dwell&&document.activeElement!==dwell)dwell.value=text(c.minimum_dwell_minutes,240);
  const confidence=document.getElementById("cycle-confidence");if(confidence&&document.activeElement!==confidence)confidence.value=text(c.minimum_confidence,70);
  document.getElementById("btn-run-cycle").disabled=Boolean(c.running);
  const consensus=state.autoConsensus||{};
  const consensusText=` Consensus: ${text(consensus.observation_count,0)} current observations · ${text(consensus.consensus_control_count,0)} controls supported${consensus.ready?" · READY":""}.`;
  const trigger=pretty(c.last_trigger||"NO EVENT YET");
  const detail=c.running
    ? `Gemini is reasoning about ${text(state.selectedSymbol)} from ${trigger}.`
    : c.last_error
      ? `${pretty(c.last_status)}: ${c.last_error}`
      : `Last trigger: ${trigger} · ${pretty(c.last_status||"NEVER_RUN")} · validated event-driven policy authority.`;
  document.getElementById("cycle-detail").textContent=`${detail}${consensusText}${models.length?` Model chain: ${models.join(" → ")}.`:""}`;
}

function renderAutonomousConsensus(){
  const root=document.getElementById("consensus-controls");
  if(!root)return;
  const c=state.autoConsensus||{};
  const autonomous=state.llmCycle?.execution_mode==="AUTONOMOUS";
  const total=Number(c.observation_count||0);
  const minObs=Number(c.minimum_observations||3);
  const minRatio=Number(c.minimum_support_ratio||0.6);
  const backendQualified=Number(c.consensus_control_count||0);
  const qualified=total>=minObs?backendQualified:0;
  const controls=Object.entries(c.controls||{}).map(([name,row])=>({name,...(row||{})}));
  const badge=document.getElementById("consensus-badge");
  const ready=Boolean(c.ready);
  badge.textContent=!autonomous?"SUPERVISED":ready?"CONSENSUS READY":total?"COLLECTING":"WAITING";
  badge.className="badge "+(!autonomous?"info":ready?"ok":total?"warn":"");
  document.getElementById("consensus-observations").textContent=text(total,0);
  document.getElementById("consensus-qualified").textContent=text(qualified,0);
  document.getElementById("consensus-threshold").textContent=`${fmt(minRatio*100,0)}%`;
  document.getElementById("consensus-epoch").textContent=c.baseline_policy_epoch==null?"—":text(c.baseline_policy_epoch);
  const lifetime=Number(c.lifetime_observation_count??total);
  const archived=Number(c.archived_window_count||0);
  const lifetimeEl=document.getElementById("consensus-lifetime");if(lifetimeEl)lifetimeEl.textContent=text(lifetime,0);
  const historyNote=document.getElementById("consensus-history-note");if(historyNote)historyNote.textContent=archived?`${archived} prior policy window${archived===1?"":"s"} archived`:"No archived windows yet";
  document.getElementById("consensus-observation-rule").textContent=total<minObs?`${minObs-total} more accepted observation${minObs-total===1?"":"s"} before consensus can qualify`:`Minimum ${minObs} observations satisfied`;
  const anchor=c.baseline_anchor?new Date(c.baseline_anchor):null;
  document.getElementById("consensus-window-age").textContent=anchor&&!Number.isNaN(anchor.getTime())?`Window started ${anchor.toLocaleString()}`:"Window not anchored yet";
  const wait=Number(state.llmCycle?.seconds_until_auto_apply_eligible||0);
  const dwellDone=wait<=0;
  document.getElementById("consensus-headline").textContent=!autonomous
    ?"Consensus is observational while application mode is supervised."
    : ready&&dwellDone
      ?`${qualified} control${qualified===1?" is":"s are"} consensus-qualified and dwell is complete.`
      : ready
        ?`${qualified} control${qualified===1?" has":"s have"} consensus; activation still waits for policy dwell.`
        : total
          ?"Gemini observations are accumulating; no control has cleared all consensus gates yet."
          :"Waiting for the first accepted Gemini observation in this dwell window.";
  document.getElementById("consensus-detail").textContent=!autonomous
    ?"Switching to autonomous mode does not automatically apply these observations; normal confidence, epoch, risk and mode-boundary gates still apply."
    : `${dwellDone?"Policy dwell complete":"Policy dwell remaining: "+age(wait)} · ${qualified} qualifying control${qualified===1?"":"s"} · each control needs ≥${fmt(minRatio*100,0)}% support and at least ${minObs} supporting observations.`;
  const historyRoot=document.getElementById("consensus-history");
  if(historyRoot){
    const windows=Array.isArray(c.recent_windows)?c.recent_windows:[];
    historyRoot.innerHTML=windows.length?windows.map(w=>{const produced=w.produced_policy_epoch;const label=w.current_window?`Baseline Epoch ${esc(text(w.baseline_policy_epoch))}`:produced?`Baseline Epoch ${esc(text(w.baseline_policy_epoch))} → Produced Epoch ${esc(text(produced))}`:`Baseline Epoch ${esc(text(w.baseline_policy_epoch))}`;const applied=w.applied_at?` · applied ${esc(new Date(w.applied_at).toLocaleString())}`:"";return `<div class="analysis-item ${w.current_window?"info":""}"><div class="row"><strong>${label}</strong><span class="badge ${w.current_window?"info":produced?"ok":""}">${w.current_window?"CURRENT WINDOW":produced?"APPLIED WINDOW":"ARCHIVED"}</span></div><div class="muted" style="margin-top:5px">${esc(text(w.observation_count,0))} accepted observation${Number(w.observation_count)===1?"":"s"}${w.last_observed_at?` · last ${esc(new Date(w.last_observed_at).toLocaleString())}`:""}${applied}${w.minimum_dwell_overridden?" · dwell override":""}</div></div>`}).join(""):`<div class="analysis-item">No policy-window history recorded yet.</div>`;
  }
  if(!controls.length){
    root.innerHTML=`<div class="consensus-empty">No controls have been proposed during the current policy dwell window yet. Prior windows remain archived below.</div>`;
    return;
  }
  controls.sort((a,b)=>Number(Boolean(b.ready))-Number(Boolean(a.ready)) || Number(b.support_ratio||0)-Number(a.support_ratio||0) || Number(b.support_count||0)-Number(a.support_count||0) || a.name.localeCompare(b.name));
  root.innerHTML=controls.map(row=>{
    const support=Number(row.support_count||0);
    const ratio=Number(row.support_ratio||0);
    const requiredNow=Math.max(minObs,Math.ceil(total*minRatio));
    const supportGap=Math.max(0,requiredNow-support);
    const globalGap=Math.max(0,minObs-total);
    const pct=Math.max(0,Math.min(100,ratio*100));
    const trulyReady=Boolean(row.ready)&&total>=minObs&&support>=minObs&&ratio>=minRatio;
    const status=trulyReady?"QUALIFIED":globalGap>0?"EARLY SUPPORT":supportGap>0?"BUILDING SUPPORT":"NOT QUALIFIED";
    const gate=trulyReady
      ?`Clears the minimum-observation and ${fmt(minRatio*100,0)}% support gates.`
      : globalGap>0
        ?`${support}/${total} currently supports this change, but consensus cannot qualify until ${globalGap} more accepted observation${globalGap===1?"":"s"} exist in this policy window.`
        : `${supportGap} more supporting observation${supportGap===1?"":"s"} needed at the current window size.`;
    return `<div class="consensus-row ${trulyReady?"ready":""}">
      <div class="consensus-name"><strong>${esc(pretty(row.name))}</strong><div class="muted">${esc(pretty(row.method||"EXACT_TARGET"))}</div></div>
      <div class="consensus-values"><span class="muted">Current</span> <strong>${esc(text(row.baseline))}</strong><br><span class="muted">Consensus</span> <strong>${esc(text(row.selected))}</strong></div>
      <div class="consensus-support"><div class="consensus-support-line"><span>${support}/${total} support</span><strong>${fmt(pct,0)}%</strong></div><div class="consensus-meter"><span style="width:${pct}%"></span></div></div>
      <div class="consensus-gate">${esc(gate)}</div>
      <span class="badge ${trulyReady?"ok":"warn"}">${esc(status)}</span>
    </div>`;
  }).join("");
}

function renderResponsiveness(){
  const r=state.responsiveness||{}, entry=r.entry_observations||{}, exit=r.exit_observations||{};
  const badge=document.getElementById("resp-badge");if(!badge)return;
  badge.textContent=text(r.profile);badge.className="badge "+(r.profile==="FAST"?"ok":r.profile==="BALANCED"?"info":"warn");
  document.getElementById("resp-pressure").textContent=r.latency_pressure_score==null?"—":`${fmt(r.latency_pressure_score,1)} / 100`;
  document.getElementById("resp-eligible").textContent=entry.eligible_rate_pct==null?"—":`${fmt(entry.eligible_rate_pct,1)}%`;
  document.getElementById("resp-hold").textContent=exit.median_holding_minutes==null?"—":`${fmt(exit.median_holding_minutes,1)} min`;
  document.getElementById("resp-capture").textContent=exit.average_mfe_capture_ratio==null?"—":`${fmt(Number(exit.average_mfe_capture_ratio)*100,1)}%`;
  document.getElementById("resp-blockers").innerHTML=(entry.dominant_block_reasons||[]).slice(0,6).map(x=>`<div class="change"><strong>${esc(pretty(x.reason))}</strong><span>${esc(text(x.count))}</span><span>${esc(fmt(x.share_pct,1))}%</span></div>`).join("")||`<div class="callout">No blocker history available yet.</div>`;
  document.getElementById("resp-levers").innerHTML=(r.candidate_levers||[]).slice(0,6).map(x=>`<div class="change" style="grid-template-columns:1fr auto"><div><strong>${esc(pretty(x.control))}</strong><div class="muted">${esc(x.effect)}</div></div><span class="badge info">${esc(pretty(x.direction))}</span></div>`).join("")||`<div class="callout">Current responsiveness has no obvious latency lever.</div>`;
  document.getElementById("resp-detail").textContent=`${pretty(r.evidence_quality||"LIMITED")} evidence · ${text(entry.history_snapshot_count,0)} market snapshots · ${text(exit.closed_trade_count,0)} closed trades. Gemini receives this analysis on every policy cycle.`;
}


function brainTab(name){
  ["runs","observations","history"].forEach(k=>{
    document.getElementById(`brain-tab-${k}`)?.classList.toggle("active",k===name);
    document.getElementById(`brain-panel-${k}`)?.classList.toggle("active",k===name);
  });
}
function closePolicyInspector(){document.getElementById("policy-inspector-modal")?.classList.remove("open")}
function policyRuntimeRows(runtime,before={}){
  const entries=Object.entries(runtime||{}).sort(([a],[b])=>a.localeCompare(b));
  return entries.map(([name,value])=>{const prior=before?.[name];const changed=prior!==undefined&&JSON.stringify(prior)!==JSON.stringify(value);return `<div class="policy-control-row ${changed?"changed":""}"><strong>${esc(pretty(name))}</strong><span>${esc(text(prior,changed?"—":""))}</span><span>${esc(text(value))}</span></div>`}).join("")||`<div class="callout">No runtime controls captured for this epoch.</div>`;
}
function openPolicyInspector(epoch){
  const apps=state.autoApplications?.applications||[];const app=apps.find(x=>Number(x.policy_epoch)===Number(epoch));if(!app)return;
  const modal=document.getElementById("policy-inspector-modal");if(!modal)return;
  document.getElementById("policy-inspector-kicker").textContent=Number(epoch)===Number(state.autoApplications?.current_command_epoch)?"ACTIVE RUNTIME POLICY":"HISTORICAL POLICY";
  document.getElementById("policy-inspector-title").textContent=`Policy Epoch ${text(epoch)}`;
  document.getElementById("policy-inspector-subtitle").textContent=`Command ${text(app.command_version)} · ${pretty(app.reconciliation)} · applied ${(app.timestamp||"").replace("T"," ").slice(0,19)}`;
  const obs=(state.policyObservations?.observations||[]).filter(o=>Number(o.baseline_policy_epoch)===Number(app.baseline_policy_epoch));
  const changes=Object.entries(app.changes||{}).map(([name,row])=>`<div class="change"><strong>${esc(pretty(name))}</strong><span>${esc(text(row?.before))}</span><span>→ ${esc(text(row?.intended))}</span></div>`).join("")||`<div class="callout">No material control patch recorded.</div>`;
  const evidence=obs.length?obs.map((o,i)=>`<div class="analysis-item"><div class="row"><strong>Observation ${esc(text(o.proposal_id||`#${i+1}`))}</strong><span class="badge info">${esc(fmt(o.overall_confidence||0,0))}%</span></div><div class="muted" style="margin-top:4px">${esc((o.observed_at||"").replace("T"," ").slice(0,19))}</div><div class="observation-changes">${Object.entries(o.changes||{}).map(([n,r])=>`<span class="observation-chip">${esc(pretty(n))}: ${esc(text(r.current))} → ${esc(text(r.proposed))}</span>`).join("")||`<span class="muted">No control mutation proposed</span>`}</div></div>`).join(""):`<div class="callout">No durable per-observation detail exists for this historical window. Atlas does not reconstruct missing Gemini prose.</div>`;
  document.getElementById("policy-inspector-body").innerHTML=`<div class="grid g3"><div class="kpi"><div class="label">Consensus observations</div><div class="value small">${esc(text(app.consensus_observation_count,0))}</div></div><div class="kpi"><div class="label">Changed controls</div><div class="value small">${Object.keys(app.changes||{}).length}</div></div><div class="kpi"><div class="label">Runtime controls captured</div><div class="value small">${Object.keys(app.runtime||{}).length}</div></div></div><div class="label" style="margin-top:16px">Applied changes</div><div class="changes" style="margin-top:8px">${changes}</div><div class="label" style="margin-top:16px">Supporting consensus observations</div><div class="analysis-list" style="margin-top:8px">${evidence}</div><div class="label" style="margin-top:16px">Full registered runtime</div><div class="policy-control-table"><div class="policy-control-row"><strong>CONTROL</strong><span>PREVIOUS</span><span>THIS EPOCH</span></div>${policyRuntimeRows(app.runtime||{},app.previous_runtime||{})}</div>`;
  modal.classList.add("open");
}
function openActivePolicyInspector(){const epoch=state.autoApplications?.current_active?.policy_epoch||state.autoApplications?.current_command_epoch;openPolicyInspector(epoch)}
function openObservationInspector(index){
  const obs=(state.policyObservations?.observations||[])[index];if(!obs)return;const modal=document.getElementById("policy-inspector-modal");if(!modal)return;
  document.getElementById("policy-inspector-kicker").textContent="GEMINI OBSERVATION";document.getElementById("policy-inspector-title").textContent=text(obs.proposal_id,"Accepted observation");document.getElementById("policy-inspector-subtitle").textContent=`Baseline epoch ${text(obs.baseline_policy_epoch)} · ${(obs.observed_at||"").replace("T"," ").slice(0,19)} · confidence ${fmt(obs.overall_confidence||0,0)}%`;
  const rows=Object.entries(obs.changes||{}).map(([name,r])=>`<div class="change"><div><strong>${esc(pretty(name))}</strong>${r?.rationale?`<div class="muted">${esc(r.rationale)}</div>`:""}</div><span>${esc(text(r?.current))}</span><span>→ ${esc(text(r?.proposed))}</span></div>`).join("")||`<div class="callout">This accepted observation recommended holding the current runtime controls.</div>`;
  const analysis=obs.analysis||{};const analysisParts=[];if((analysis.performance_diagnosis||[]).length)analysisParts.push(`<strong>Performance diagnosis</strong><br>${esc(analysis.performance_diagnosis.join(" · "))}`);if((analysis.responsiveness_diagnosis||[]).length)analysisParts.push(`<strong>Responsiveness</strong><br>${esc(analysis.responsiveness_diagnosis.join(" · "))}`);if((analysis.weaknesses_targeted||[]).length)analysisParts.push(`<strong>Targets</strong><br>${esc(analysis.weaknesses_targeted.join(" · "))}`);if(analysis.critic_verdict||analysis.critic_summary)analysisParts.push(`<strong>Critic</strong><br>${esc(text(analysis.critic_verdict))} — ${esc(text(analysis.critic_summary))}`);
  document.getElementById("policy-inspector-body").innerHTML=`${analysisParts.length?`<div class="callout">${analysisParts.join("<br><br>")}</div>`:`<div class="callout">This legacy observation predates durable Gemini-analysis storage. Atlas shows the confidence and proposed controls that were actually preserved and does not reconstruct missing prose.</div>`}<div class="label" style="margin-top:16px">Observed control recommendations</div><div class="changes" style="margin-top:8px">${rows}</div>`;modal.classList.add("open");
}

function openGeminiRunInspector(index){
  const runs=Array.isArray(state.llmCycle?.run_history)?[...state.llmCycle.run_history].reverse():[];
  const run=runs[index];if(!run)return;
  const modal=document.getElementById("policy-inspector-modal");if(!modal)return;
  document.getElementById("policy-inspector-kicker").textContent="GEMINI POLICY RUN";
  document.getElementById("policy-inspector-title").textContent=`Run #${text(run.run_number)} · ${pretty(run.outcome||run.status)}`;
  document.getElementById("policy-inspector-subtitle").textContent=`Baseline epoch ${text(run.baseline_policy_epoch)} · ${(run.completed_at||"").replace("T"," ").slice(0,19)} · ${fmt(run.overall_confidence||0,0)}% confidence`;
  const changes=Object.entries(run.changes||{}).map(([name,row])=>`<div class="change"><div><strong>${esc(pretty(name))}</strong>${row?.rationale?`<div class="muted">${esc(row.rationale)}</div>`:""}</div><span>${esc(text(row?.current))}</span><span>→ ${esc(text(row?.proposed))}</span></div>`).join("")||`<div class="callout">No material runtime mutation was proposed by this run.</div>`;
  const deferred=(run.deferred_locked_changes||[]).map(row=>{const name=row?.name||row?.control||row?.parameter||"position-sensitive control";return `<div class="change"><div><strong>${esc(pretty(name))}</strong><div class="muted">Deferred while existing-position policy locks remain authoritative.</div></div><span>${esc(text(row?.current))}</span><span>DEFERRED</span></div>`}).join("");
  const a=run.analysis||{};const parts=[];if((a.performance_diagnosis||[]).length)parts.push(`<strong>Performance</strong><br>${esc(a.performance_diagnosis.join(" · "))}`);if((a.responsiveness_diagnosis||[]).length)parts.push(`<strong>Responsiveness</strong><br>${esc(a.responsiveness_diagnosis.join(" · "))}`);if((a.weaknesses_targeted||[]).length)parts.push(`<strong>Targets</strong><br>${esc(a.weaknesses_targeted.join(" · "))}`);
  const consensus=run.consensus_observation_recorded?`Accepted consensus observation recorded · window became ${text(run.consensus_observation_count_after_run,0)} of ${text(run.consensus_minimum_observations,3)} minimum · ${text(run.consensus_control_count_after_run,0)} qualifying controls.`:"This run did not create an accepted consensus observation.";
  document.getElementById("policy-inspector-body").innerHTML=`<div class="callout"><strong>Outcome</strong> ${esc(pretty(run.outcome||run.status))}${run.autonomous_status?` · ${esc(pretty(run.autonomous_status))}`:""}<br><strong>Consensus</strong> ${esc(consensus)}${run.critic_verdict?`<br><strong>Critic</strong> ${esc(pretty(run.critic_verdict))}${run.critic_summary?` — ${esc(run.critic_summary)}`:""}`:""}</div>${parts.length?`<div class="callout" style="margin-top:10px">${parts.join("<br><br>")}</div>`:""}<div class="label" style="margin-top:16px">Proposed runtime changes</div><div class="changes" style="margin-top:8px">${changes}</div>${deferred?`<div class="label" style="margin-top:16px">Deferred locked changes</div><div class="changes" style="margin-top:8px">${deferred}</div>`:""}`;
  modal.classList.add("open");
}

function renderAtlas(){
  const p=state.proposal||{}, rs=p.review_summary||{}, ev=rs.shadow_evidence||{}, st=rs.stability||{};
  const lifecycle=p.lifecycle?.state||p.review_state;const applications=state.autoApplications||{};const active=applications.current_active||null;const consensus=state.autoConsensus||{};
  const runtime=applications.current_status_runtime&&Object.keys(applications.current_status_runtime).length?applications.current_status_runtime:(active?.runtime||applications.current_command_runtime||{});
  document.getElementById("runtime-policy-epoch").textContent=text(applications.current_status_epoch||active?.policy_epoch||applications.current_command_epoch);
  document.getElementById("runtime-policy-command").textContent=text(active?.command_version||state.command?.command_version);
  document.getElementById("runtime-policy-count").textContent=text(Object.keys(runtime||{}).length,0);
  const reconciliation=active?.reconciliation||((applications.current_status_epoch===applications.current_command_epoch)?"RUNTIME_CONFIRMED":"AWAITING_RUNTIME");
  document.getElementById("runtime-policy-reconciliation").textContent=pretty(reconciliation);const rb=document.getElementById("runtime-policy-badge");rb.textContent=pretty(reconciliation);rb.className="badge "+(String(reconciliation).includes("CONFIRMED")?"ok":String(reconciliation).includes("MISMATCH")?"bad":"warn");
  const activeChanges={};Object.entries(active?.changes||{}).forEach(([name,row])=>activeChanges[name]={current:row?.before,shadow:row?.registered??row?.intended});renderProposalChanges("runtime-policy-changes",activeChanges);
  const supporting=(state.policyObservations?.observations||[]).filter(o=>Number(o.baseline_policy_epoch)===Number(active?.baseline_policy_epoch));
  const integrity=String(active?.consensus_gate_integrity||"VERIFIED");
  document.getElementById("runtime-policy-rationale").textContent=active
    ? integrity==="LEGACY_BYPASS"
      ? `Epoch ${text(active.policy_epoch)} was applied from baseline epoch ${text(active.baseline_policy_epoch)} with only ${text(active.consensus_observation_count,0)} / ${text(active.consensus_minimum_observations,3)} accepted observations under the pre-1.30.43 autonomous-bootstrap bug. Atlas preserves this active runtime but will not permit the next mature-epoch mutation to bypass consensus.`
      : `Epoch ${text(active.policy_epoch)} was produced from baseline epoch ${text(active.baseline_policy_epoch)} using ${text(active.consensus_observation_count,0)} accepted observations. ${supporting.length?`${supporting.length} supporting observation records are available to inspect.`:"Older full Gemini prose is not reconstructed when it was not durably stored."}`
    : "No autonomous policy application is currently registered.";

  document.getElementById("a-candidate").textContent=text(p.selected_candidate);document.getElementById("a-readiness").textContent=pretty(lifecycle||"—");document.getElementById("a-epoch").textContent=text(p.current_policy_epoch??state.command?.policy_epoch);document.getElementById("a-confidence").textContent=rs.confidence==null?"—":fmt(rs.confidence,1)+"%";
  const llm=p.llm_policy||{},bundle=llm.bundle||{},critic=llm.critic||{};const diagnoses=bundle.performance_diagnosis||rs.performance_diagnosis||[];const weaknesses=bundle.weaknesses_targeted||rs.weaknesses_targeted||[];const speed=bundle.responsiveness_diagnosis||rs.responsiveness_diagnosis||[];
  document.getElementById("atlas-llm-evidence").innerHTML=llm.proposal_id?`<strong>Latest Gemini + critic analysis</strong><br>${esc((diagnoses.length?diagnoses:["No performance diagnosis supplied."]).join(" · "))}${speed.length?`<br><span class="muted">Responsiveness (${esc(text(bundle.responsiveness_profile||rs.responsiveness_profile))}): ${esc(speed.join(" · "))}</span>`:""}<br><span class="muted">Targets: ${esc((weaknesses.length?weaknesses:["not specified"]).join(" · "))} · Critic: ${esc(text(critic.verdict||rs.critic_verdict))} — ${esc(text(critic.summary||rs.critic_summary,"No summary"))}</span>`:"No Gemini analysis attached to the latest proposal.";
  const blockers=p.recommendation_blockers||[];document.getElementById("a-blockers").textContent=blockers.length?`Latest candidate blockers: ${blockers.map(pretty).join(" · ")}`:"Latest candidate has no recommendation blockers.";
  document.getElementById("a-risk").textContent=text(p.risk?.state||rs.risk_state);document.getElementById("a-evidence").textContent=text(ev.quality);document.getElementById("a-stability").textContent=st.stable?"STABLE":"NOT STABLE";document.getElementById("a-review-state").textContent=pretty(lifecycle||"—");

  const registry=document.getElementById("policy-registry-list");const apps=Array.isArray(applications.applications)?applications.applications:[];if(registry)registry.innerHTML=apps.length?apps.map(app=>{const isActive=Number(app.policy_epoch)===Number(applications.current_command_epoch);const changes=Object.entries(app.changes||{});const detail=changes.length?changes.slice(0,4).map(([n,r])=>`${pretty(n)} ${text(r?.before)} → ${text(r?.intended)}`).join(" · ")+(changes.length>4?` · +${changes.length-4} more`:""):"No material control patch recorded";const cls=String(app.reconciliation||"").includes("MISMATCH")?"bad":String(app.reconciliation||"").includes("CONFIRMED")?"ok":"warn";const integrity=String(app.consensus_gate_integrity||"VERIFIED");return `<div class="policy-record ${isActive?"active":""}" onclick="openPolicyInspector(${Number(app.policy_epoch)||0})"><div class="policy-record-head"><div><strong>Epoch ${esc(text(app.policy_epoch))}</strong>${isActive?` <span class="badge ok">ACTIVE</span>`:""}${integrity==="LEGACY_BYPASS"?` <span class="badge bad">PRE-FIX CONSENSUS BYPASS</span>`:""}</div><span class="badge ${cls}">${esc(pretty(app.reconciliation))}</span></div><div class="policy-record-meta"><span>Command ${esc(text(app.command_version))}</span><span>${esc((app.timestamp||"").replace("T"," ").slice(0,19))}</span><span>${esc(text(app.consensus_observation_count,0))} / ${esc(text(app.consensus_minimum_observations,3))} accepted observations</span></div><div class="policy-record-changes">${esc(detail)}</div></div>`}).join(""):`<div class="callout">No autonomous policy applications recorded yet.</div>`;

  const pc=document.getElementById("policy-consensus-summary");
  const consensusRows=Array.isArray(consensus.controls)
    ? consensus.controls
    : Object.entries(consensus.controls||{}).map(([name,row])=>({name,...(row||{})}));
  const consensusTotal=Number(consensus.observation_count||0);
  const consensusSupportThreshold=Number(consensus.minimum_support_ratio||.6);
  const consensusMinObservations=Number(consensus.minimum_observations||consensus.minimum_observation_count||0);
  if(pc){
    const readiness=Number(consensus.consensus_control_count||0)>0
      ?"One or more candidate controls have reached consensus."
      :"Atlas is still accumulating support; the runtime policy remains unchanged.";
    pc.innerHTML=`<div class="consensus-overview">
      <div><span class="label">Baseline policy</span><strong>Epoch ${esc(text(consensus.baseline_policy_epoch))}</strong></div>
      <div><span class="label">Accepted observations</span><strong>${esc(text(consensusTotal,0))}${consensusMinObservations?` of ${esc(text(consensusMinObservations))} minimum`:""}</strong></div>
      <div><span class="label">Support threshold</span><strong>${fmt(consensusSupportThreshold*100,0)}%</strong></div>
      <div><span class="label">Qualified controls</span><strong>${esc(text(consensus.consensus_control_count,0))}</strong></div>
    </div><div class="muted" style="margin-top:9px">${esc(readiness)}</div>`;
  }
  const pcr=document.getElementById("policy-consensus-controls");
  if(pcr){
    pcr.innerHTML=consensusRows.length?consensusRows.map((row,index)=>{
      const support=Number(row.support_count||0);
      const pct=consensusTotal?support/consensusTotal*100:0;
      const ready=Boolean(row.consensus_ready);
      const required=Math.max(1,Math.ceil(consensusTotal*consensusSupportThreshold));
      const supportGap=Math.max(0,required-support);
      const status=ready?"QUALIFIED":supportGap===0?"AWAITING WINDOW":"BUILDING SUPPORT";
      const gate=ready
        ?"Support and observation requirements are satisfied for this control."
        : supportGap===0
          ?"Support ratio is sufficient; another consensus requirement is still pending."
          : `${supportGap} more supporting observation${supportGap===1?"":"s"} needed at the current window size.`;
      const method=pretty(row.method||row.selection_method||"EXACT_TARGET");
      return `<article class="consensus-card ${ready?"ready":""}">
        <div class="consensus-card-head">
          <div><span class="label">Candidate control ${index+1}</span><strong>${esc(pretty(row.name||row.control||"Unnamed control"))}</strong><div class="muted">${esc(method)}</div></div>
          <span class="badge ${ready?"ok":"warn"}">${esc(status)}</span>
        </div>
        <div class="consensus-value-grid">
          <div><span class="label">Active runtime</span><strong>${esc(text(row.baseline??row.current))}</strong></div>
          <div><span class="label">Consensus candidate</span><strong>${esc(text(row.selected??row.proposed))}</strong></div>
        </div>
        <div class="consensus-support-block">
          <div class="consensus-support-line"><span>${support} / ${consensusTotal} observations support this value</span><strong>${fmt(pct,0)}%</strong></div>
          <div class="consensus-meter"><span style="width:${Math.min(100,pct)}%"></span></div>
        </div>
        <div class="consensus-gate"><strong>Gate</strong><span>${esc(gate)}</span></div>
      </article>`;
    }).join(""):`<div class="consensus-empty">No control mutations are currently accumulating consensus. The active runtime policy remains unchanged.</div>`;
  }

  const brainEvents=state.brainEvents||{};
  const bootstrap=brainEvents.bootstrap||{};
  const bb=document.getElementById("bootstrap-badge");
  if(bb){bb.textContent=pretty(bootstrap.state||"UNKNOWN");bb.className="badge "+(bootstrap.qualified?"ok":bootstrap.pending?"warn":"info");}
  const bs=document.getElementById("bootstrap-state");if(bs)bs.textContent=pretty(bootstrap.state||"—");
  const bbud=document.getElementById("bootstrap-budget");if(bbud)bbud.textContent=text(bootstrap.bootstrap_change_budget,12);
  const ba=document.getElementById("bootstrap-authority");if(ba)ba.textContent=pretty(bootstrap.seed_configuration_authority||"UNQUALIFIED SEED");
  const bc=document.getElementById("bootstrap-copy");if(bc)bc.textContent=bootstrap.qualified
    ?"The starting Nyao runtime has been explicitly qualified by Gemini + Critic. Future changes use the normal event-driven incremental budget."
    :bootstrap.state==="WAITING_FOR_LIVE_MARKET"
      ?"Atlas will not calibrate the initial baseline from stale closed-market quotes. Qualification arms when a fresh tradable market snapshot is available. Existing established accounts continue trading; brand-new accounts require qualification first."
      :"Initial policy qualification is pending. Nyao defaults are treated as seed values, not presumed-correct strategy truth.";
  const pendingEvents=(brainEvents.event_bus?.pending_events||[]);
  const eqb=document.getElementById("event-queue-badge");if(eqb){eqb.textContent=`${pendingEvents.length} PENDING`;eqb.className="badge "+(pendingEvents.some(e=>e.priority==="P0")?"bad":pendingEvents.length?"warn":"ok");}
  const eq=document.getElementById("event-queue");if(eq)eq.innerHTML=pendingEvents.length?pendingEvents.slice(0,8).map(e=>`<div class="change"><div><strong>${esc(pretty(e.event))}</strong><div class="muted">${esc(pretty(e.priority))} · ${esc((e.created_at||"").replace("T"," ").slice(0,19))}</div></div><span>${esc(pretty(e.payload?.from||e.payload?.failure_type||e.payload?.unit?.result_class||"MATERIAL"))}</span><span>→ BRAIN</span></div>`).join(""):`<div class="callout">No pending material events. Atlas is observing without spending Gemini cycles.</div>`;

  const lifecycleRows=Array.isArray(state.status?.recent_lifecycle_events)?state.status.recent_lifecycle_events:[];
  const lifecycleVersion=String(state.status?.lifecycle_contract_version||"");
  const lifecycleFailures=lifecycleRows.filter(e=>["FAILED","REJECTED"].includes(String(e?.result||"").toUpperCase()));
  const lcb=document.getElementById("lifecycle-contract-badge");if(lcb){lcb.textContent=lifecycleVersion?"AUTHORITATIVE":"LEGACY / WAITING";lcb.className="badge "+(lifecycleVersion?"ok":"warn");}
  const lcv=document.getElementById("lifecycle-contract-version");if(lcv)lcv.textContent=lifecycleVersion||"—";
  const lci=document.getElementById("lifecycle-contract-instance");if(lci){const ep=Number(state.status?.lifecycle_contract_started_at_epoch||0);lci.textContent=ep?new Date(ep*1000).toLocaleString():"—";}
  const lce=document.getElementById("lifecycle-contract-events");if(lce)lce.textContent=String(lifecycleRows.length);
  const lcf=document.getElementById("lifecycle-contract-failures");if(lcf)lcf.textContent=String(lifecycleFailures.length);
  const lcc=document.getElementById("lifecycle-contract-copy");if(lcc)lcc.textContent=lifecycleVersion
    ?(lifecycleFailures.length?`${lifecycleFailures.length} explicit NYAO execution/management failure event${lifecycleFailures.length===1?"":"s"} are present in the recent contract window. Affected risk units are excluded from strategy learning.`:"Lifecycle telemetry is authoritative and the recent event window contains no explicit implementation failures.")
    :"This EA has not published the P3.57 lifecycle contract yet. Atlas will keep legacy outcomes UNKNOWN rather than assume they were clean.";

  const windowRoot=document.getElementById("policy-window-history");
  if(windowRoot){
    const windows=Array.isArray(consensus.recent_windows)?consensus.recent_windows:[];
    windowRoot.innerHTML=windows.length?`<div class="label" style="margin-top:14px">Policy learning windows</div><div class="policy-window-list">${windows.map(w=>{const produced=w.produced_policy_epoch;return `<div class="policy-window-row ${w.current_window?"current":""}"><div><strong>Baseline Epoch ${esc(text(w.baseline_policy_epoch))}${produced?` → Epoch ${esc(text(produced))}`:""}</strong><div class="muted">${esc(text(w.observation_count,0))} accepted observation${Number(w.observation_count)===1?"":"s"}${w.applied_at?` · applied ${esc(new Date(w.applied_at).toLocaleString())}`:""}</div></div><span class="badge ${w.current_window?"info":produced?"ok":"warn"}">${w.current_window?"CURRENT":produced?"PRODUCED POLICY":"ARCHIVED"}</span></div>`}).join("")}</div>`:"";
  }

  const runsRoot=document.getElementById("gemini-run-history");
  if(runsRoot){
    const runs=Array.isArray(state.llmCycle?.run_history)?[...state.llmCycle.run_history].reverse():[];
    runsRoot.innerHTML=runs.length?runs.map((run,i)=>{const changes=Object.keys(run.changes||{});const outcome=String(run.outcome||run.status||"UNKNOWN");const cls=outcome==="APPLIED"?"ok":outcome==="FAILED"||outcome==="REJECTED"?"bad":outcome==="DEFERRED"?"warn":"info";const obs=run.consensus_observation_recorded?`Observation ${text(run.consensus_observation_count_after_run,0)} / ${text(run.consensus_minimum_observations,3)}`:"No consensus observation";return `<div class="gemini-run-row" onclick="openGeminiRunInspector(${i})"><div class="gemini-run-head"><div><strong>Run #${esc(text(run.run_number))}</strong><div class="muted">Baseline Epoch ${esc(text(run.baseline_policy_epoch))} · ${esc((run.completed_at||"").replace("T"," ").slice(0,19))} · ${esc(pretty(run.trigger||"SCHEDULED"))}</div></div><span class="badge ${cls}">${esc(pretty(outcome))}</span></div><div class="gemini-run-meta"><span>${fmt(run.overall_confidence||0,0)}% confidence</span><span>${esc(obs)}</span><span>${changes.length?`${changes.length} proposed control${changes.length===1?"":"s"}`:"No material change"}</span>${run.critic_verdict?`<span>Critic ${esc(pretty(run.critic_verdict))}</span>`:""}</div></div>`}).join(""):`<div class="callout">Run-level lineage begins with Atlas 1.30.44. Earlier runs remain represented by accepted observations and applied-policy history where those records exist.</div>`;
  }

  const obsRoot=document.getElementById("policy-observation-list");const observations=state.policyObservations?.observations||[];if(obsRoot)obsRoot.innerHTML=observations.length?observations.map((o,i)=>{const ch=Object.entries(o.changes||{});return `<div class="observation-row" onclick="openObservationInspector(${i})"><div class="row"><div><strong>${esc(text(o.proposal_id,"Accepted Gemini observation"))}</strong><div class="muted">Baseline epoch ${esc(text(o.baseline_policy_epoch))} · ${esc((o.observed_at||"").replace("T"," ").slice(0,19))}</div></div><span class="badge info">${fmt(o.overall_confidence||0,0)}%</span></div><div class="observation-changes">${ch.length?ch.slice(0,5).map(([n,r])=>`<span class="observation-chip">${esc(pretty(n))}: ${esc(text(r.current))} → ${esc(text(r.proposed))}</span>`).join(""):`<span class="muted">Hold observation · no runtime mutation</span>`}</div></div>`}).join(""):`<div class="callout">No accepted Gemini observations have been recorded yet.</div>`;

}

function renderParameterIntelligence(){
  const p=state.parameterIntel||{}, r=p.registry||{}, domains=p.domain_maturity||{};
  const count=document.getElementById("pi-count"); if(!count)return;
  count.textContent=text(r.parameter_count,157);
  document.getElementById("pi-locked").textContent=text(r.position_sensitive_count,53);
  document.getElementById("pi-budget").textContent=text(p.change_budget??r.change_budget,3);
  const autonomous=state.llmCycle?.execution_mode==="AUTONOMOUS";
  document.getElementById("pi-exec").textContent=autonomous?"ENABLED":"SUPERVISED";
  document.getElementById("pi-authority-note").textContent=autonomous
    ? "Historical value/outcome differences are descriptive associations, not causal proof. Gemini changes require critic acceptance, schema validation, confidence and dwell checks, a current policy epoch, and a clean mode boundary before Atlas can apply them."
    : "Historical value/outcome differences are descriptive associations, not causal proof. Gemini can propose validated numeric changes, but human approval and application remain required in supervised mode.";
  document.getElementById("pi-real-changes").textContent=text(p.current_advisor_change_count,0);
  document.getElementById("pi-noop").textContent=text(p.no_op_advisor_changes_filtered,0);

  document.getElementById("pi-domains").innerHTML=Object.entries(domains).map(([name,v])=>{
    const dist=v.distribution||{};
    const detail=`${text(v.mature_or_moderate_parameters,0)}/${text(v.parameter_count,0)} moderate+ · ${text(dist.MATURE,0)} mature`;
    return `<div class="change"><div><strong>${esc(pretty(name))}</strong><div class="muted">${esc(detail)}</div></div><span class="badge ${v.level==="MATURE"?"ok":v.level==="MODERATE"?"info":"warn"}">${esc(text(v.level))}</span></div>`
  }).join("")||`<div class="callout">No evidence maturity calculated yet.</div>`;

  const candidates=[...(p.supervised_candidates||[]),...(p.top_investigation_candidates||[])].slice(0,10);
  document.getElementById("pi-candidates").innerHTML=candidates.map(c=>{
    const maturity=c.parameter_maturity||{};
    const assoc=c.descriptive_association||{};
    const why=(c.why_relevant||[])[0]||"No direct relevance reason yet.";
    const caution=(c.why_not_change||[])[0]||"";
    const assocText=assoc.available?`${pretty(assoc.strength)} association · Δ mean P/L ${text(assoc.mean_pl_gap)}`:"no comparable value/outcome groups";
    return `<div class="change" style="align-items:flex-start">
      <div style="min-width:0">
        <strong>${esc(c.label||pretty(c.parameter))}</strong>
        <div class="muted">${esc(pretty(c.domain))} · ${esc(pretty(c.family||""))}${c.position_sensitive?" · policy locked":""}</div>
        <div class="muted" style="margin-top:5px">${esc(why)}</div>
        ${caution?`<div class="muted" style="margin-top:3px">Hold: ${esc(caution)}</div>`:""}
        <div class="muted" style="margin-top:3px">${esc(assocText)} · values ${esc(text(maturity.distinct_values,0))} · outcomes ${esc(text(maturity.outcomes_with_value,0))}</div>
      </div>
      <div style="text-align:right;flex:0 0 auto">
        <span class="badge ${c.action==="CURRENT_ADVISOR_PROPOSAL"?"ok":c.readiness==="WAIT_FOR_EVIDENCE"?"warn":"info"}">${esc(c.action==="CURRENT_ADVISOR_PROPOSAL"?"PROPOSED":c.readiness==="WAIT_FOR_EVIDENCE"?"WAIT":"INVESTIGATE")}</span>
        <div class="muted" style="margin-top:4px">${c.proposed!==null&&c.proposed!==undefined?`${esc(text(c.current))} → ${esc(text(c.proposed))}`:`score ${esc(text(c.relevance_score))}`}</div>
        <div class="muted">${esc(text(c.evidence_maturity))}</div>
      </div>
    </div>`
  }).join("")||`<div class="callout">No candidates yet.</div>`;
}
function renderControl(){
  // Legacy supervised-control renderer retained for backend/UI compatibility only.
  // P3.54+ uses the event-driven autonomous Brain UI, so these elements may not
  // exist. Never allow an absent legacy panel to break the dashboard refresh.
  const ab=document.getElementById("arm-badge");
  if(!ab)return;
  const c=state.command||{}, arm=state.arm||{};
  ab.textContent=arm.armed?"ARMED":"DISARMED";
  ab.className="badge "+(arm.armed?"ok":"bad");
  document.getElementById("arm-detail").textContent=arm.armed
    ? `Armed by ${text(arm.armed_by)} · ${Math.ceil(Number(arm.remaining_seconds||0)/60)} min remaining`
    : "Execution is fail-closed until explicitly armed.";
  document.getElementById("btn-arm").disabled=Boolean(arm.armed);
  document.getElementById("btn-disarm").disabled=!arm.armed;
  document.getElementById("c-version").textContent=text(c.command_version);
  document.getElementById("c-epoch").textContent=text(c.policy_epoch);
  document.getElementById("c-lot").textContent=text(c.base_lot_size);
  document.getElementById("c-enabled").textContent=c.enabled===false?"NO":"YES";
  const pkg=state.supervised?.supervised_command_proposal||state.supervised;
  const packageEvents=(state.executionEvents?.events||[]).filter(e=>e.supervised_command_id===pkg?.supervised_command_id);
  const completedEvent=packageEvents.find(e=>["EXECUTED","EXECUTED_RECOVERED"].includes(e.action));
  const ackEvent=packageEvents.find(e=>String(e.action||"").startsWith("NYAO_ACK_"));
  const packageLifecycle=ackEvent?.action==="NYAO_ACK_CONFIRMED"?"APPLIED":completedEvent?"AWAITING_NYAO_ACK":pkg?.state;
  const eb=document.getElementById("exec-badge");
  if(pkg?.supervised_command_id){eb.textContent=text(packageLifecycle);eb.className="badge "+badgeClass(packageLifecycle);
    document.getElementById("exec-summary").innerHTML=packageLifecycle==="APPLIED"
      ? `<strong>Policy applied and confirmed by Nyao</strong><br>Command ${esc(text(pkg.command_preview?.hypothetical_command_version))} / policy epoch ${esc(text(pkg.command_preview?.target_policy_epoch))} · package ${esc(pkg.supervised_command_id)}.`
      : `<strong>Command package ${esc(pkg.supervised_command_id)}</strong><br>Baseline ${esc(text(pkg.current_context?.baseline_command_version))} / epoch ${esc(text(pkg.current_context?.baseline_policy_epoch))} → command ${esc(text(pkg.command_preview?.hypothetical_command_version))} / epoch ${esc(text(pkg.command_preview?.target_policy_epoch))}.`;
  } else {eb.textContent="NO PACKAGE";eb.className="badge";document.getElementById("exec-summary").textContent="Build an approved command package from the Atlas page first."}
  const ex=state.execution, ack=state.ack;
  const executionState=ex?.status||(completedEvent?completedEvent.action:"WAITING");
  const ackMatchesExecution=Boolean(
    ack && completedEvent && ack.execution_id===completedEvent.execution_id
  );
  const ackState=ackMatchesExecution
    ? ack.state
    : ackEvent
      ? String(ackEvent.action).replace("NYAO_ACK_","")
      : "WAITING";
  const steps=[
    ["Package",pkg?"READY":"WAITING"],
    ["Preflight",(state.preflight?.ready_for_supervised_execution??state.preflight?.ready_for_explicit_demo_execution)?"PASS":"WAITING"],
    ["Execution",executionState],
    ["Nyao ACK",ackState]
  ];
  document.getElementById("exec-workflow").innerHTML=steps.map((x,i)=>`<div class="step ${badgeClass(x[1])==="ok"?"done":""}"><div class="step-num">${i+1}</div><div><strong>${x[0]}</strong></div><span class="badge ${badgeClass(x[1])}">${esc(text(x[1]))}</span></div>`).join("");
  document.getElementById("btn-preflight").disabled=!pkg||Boolean(completedEvent);
  document.getElementById("btn-execute").disabled=!pkg||Boolean(completedEvent);
  document.getElementById("btn-ack").disabled=!completedEvent||ackState==="CONFIRMED";
  document.getElementById("btn-execute").textContent=completedEvent?"Policy applied":"Execute policy";
  document.getElementById("btn-ack").textContent=ackState==="CONFIRMED"?"Nyao confirmed":"Refresh Nyao ACK";
  renderRiskAppetite();
}
function renderRiskAppetite(){
  const ra=state.riskAppetite||{};
  const capital=state.zonePlan?.capital_sizing||state.intelligence?.capital_sizing||state.intelligence?.capital||{};
  const pct=Number(ra.portfolio_hard_risk_pct??capital.risk_appetite?.portfolio_hard_risk_pct??1);
  const equity=Number(state.status?.equity||capital.equity||0);
  const hard=Number(capital.maximum_total_strategy_risk_amount||equity*pct/100);
  const operating=Number(capital.portfolio_allocation?.operating_risk_ceiling_amount||0);
  const badge=document.getElementById("risk-appetite-badge");
  if(!badge)return;
  badge.textContent=`${fmt(pct,2)}%`;
  badge.className="badge "+(pct>=10?"bad":pct>=5?"warn":"info");
  document.getElementById("risk-appetite-current").textContent=`${fmt(pct,2)}%`;
  document.getElementById("risk-appetite-amount").textContent=money(hard);
  document.getElementById("risk-appetite-operating").textContent=operating>0?money(operating):"—";
  const input=document.getElementById("risk-appetite-input");
  if(input && document.activeElement!==input)input.value=String(pct);
  const warning=document.getElementById("risk-appetite-warning");
  warning.textContent=pct>=10
    ?`HIGH RISK CEILING · ${fmt(pct,2)}% allows substantial simultaneous strategy risk. Atlas still scales the operating envelope and individual units independently.`
    :pct>=5
      ?`Elevated risk ceiling · ${fmt(pct,2)}%. This expands aggregate capacity, not per-trade risk. Atlas safety governors remain active.`
      :"Only you can increase this ceiling. Gemini and autonomous policy are not permitted to raise it.";
}
async function loadRiskAppetite(){
  try{state.riskAppetite=await api("/api/v1/atlas/risk-appetite")}catch(e){console.warn("Risk appetite refresh failed",e)}
}
async function saveRiskAppetite(){
  const input=document.getElementById("risk-appetite-input");
  const pct=Number(input?.value);
  if(!Number.isFinite(pct)||pct<1||pct>20)return toast("Risk ceiling must be between 1% and 20%.",true);
  const equity=Number(state.status?.equity||0);
  const amount=equity>0?equity*pct/100:0;
  const current=Number(state.riskAppetite?.portfolio_hard_risk_pct||1);
  const msg=pct>current
    ?`Increase Atlas maximum aggregate portfolio risk from ${fmt(current,2)}% to ${fmt(pct,2)}%${amount>0?` (about ${money(amount)} at current equity)`:""}?`
    :`Set Atlas maximum aggregate portfolio risk to ${fmt(pct,2)}%?`;
  if(!confirm(msg))return;
  try{
    state.riskAppetite=await api("/api/v1/atlas/risk-appetite",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({portfolio_hard_risk_pct:pct,actor:"Nobel"})});
    await loadIntelligence();
    renderAll();
    toast(`Portfolio hard risk ceiling set to ${fmt(pct,2)}%.`);
  }catch(e){toast(e.message,true)}
}
function renderControls(){
  const q=document.getElementById("control-search")?.value?.trim().toLowerCase()||"";
  const root=document.getElementById("runtime-controls");if(!root)return;
  root.innerHTML=CONTROL_CONFIG.map((g,gi)=>{
    const cs=(g.controls||[]).filter(c=>!q||(`${c.label} ${c.name}`).toLowerCase().includes(q));
    if(!cs.length)return"";
    return `<details class="control-group" ${q?"open":""}><summary>${esc(g.name)} <span class="muted">· ${cs.length}</span></summary><div class="control-grid">${cs.map(c=>controlHtml(c)).join("")}</div></details>`;
  }).join("");
  updateDirtyCount();
}
function controlHtml(c){
  const actual=state.dirty.hasOwnProperty(c.name)?state.dirty[c.name]:effectiveControl(c);
  let input="";
  if(c.kind==="bool"){input=`<select onchange="editControl('${c.name}',this.value==='true',this)"><option value="true" ${actual===true?"selected":""}>On</option><option value="false" ${actual===false?"selected":""}>Off</option></select>`}
  else if(c.kind==="select"){input=`<select onchange="editControl('${c.name}',Number(this.value),this)">${(c.options||[]).map(o=>`<option value="${o.value}" ${Number(actual)===Number(o.value)?"selected":""}>${esc(o.label)}</option>`).join("")}</select>`}
  else if(c.kind==="time"||c.kind==="string"){input=`<input value="${esc(text(actual,""))}" onchange="editControl('${c.name}',this.value,this)">`}
  else {input=`<input type="number" value="${esc(text(actual,""))}" min="${c.min??""}" max="${c.max??""}" step="${c.step??"any"}" onchange="editControl('${c.name}',Number(this.value),this)">`}
  return `<div class="control ${state.dirty.hasOwnProperty(c.name)?"dirty":""}"><label>${esc(c.label)}</label>${input}</div>`;
}
function effectiveControl(c){const s=state.status||{},cmd=state.command||{};return cmd[c.name]!==undefined?cmd[c.name]:s[c.status_key]}
function editControl(k,v,el){
  state.dirty[k]=v;
  const control=el?.closest(".control");
  if(control)control.classList.add("dirty");
  updateDirtyCount();
}
function updateDirtyCount(){const n=Object.keys(state.dirty).length;const e=document.getElementById("dirty-count");if(e)e.textContent=n?`${n} unsaved change${n===1?"":"s"}`:"No unsaved changes"}
function discardEdits(){state.dirty={};renderControls()}
async function applyEdits(){
  const n=Object.keys(state.dirty).length;
  if(!n)return toast("No runtime changes to apply.");
  if(!confirm(`Apply ${n} runtime change${n===1?"":"s"} through the Atlas command API?`))return;

  try{
    const result=await api("/api/v1/nyao/command",{
      method:"PUT",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify(state.dirty)
    });

    state.command=result?.command||result;
    state.dirty={};

    // renderAll() intentionally avoids rebuilding the 157-control editor on
    // every polling refresh. After a successful save, force one rebuild so
    // dirty styling and the unsaved-change counter are cleared immediately.
    loadNotificationSettings();
    renderAll();
    renderControls();
    evaluateNotifications();

    toast("Runtime changes applied.");
  }catch(e){
    toast(e.message,true);
  }
}

async function loadReview(){
  const p=state.proposal;if(!p?.proposal_id){state.review=null;return}
  try{state.review=await api(`/api/v1/atlas/advisory-proposals/${p.proposal_id}/review`)}catch{state.review=null}
}
async function loadSupervised(){
  const proposalId=state.proposal?.proposal_id;
  if(!proposalId){state.supervised=null;return}
  try{
    const data=await api("/api/v1/atlas/supervised-command-proposals?limit=100");
    const rows=data.proposals||data.supervised_command_proposals||[];
    state.supervised=rows.find(x=>(x.source||{}).proposal_id===proposalId)||null;
  }catch(e){console.warn("Command package refresh failed",e)}
}
async function loadLlmCycle(){
  const results=await Promise.allSettled([
    api("/api/v1/atlas/llm/cycle-schedule"),
    api("/api/v1/atlas/llm/status"),
    api("/api/v1/atlas/autonomous-policy-consensus"),
    api("/api/v1/atlas/autonomous-policy-observations?limit=200")
  ]);
  if(results[0].status==="fulfilled")state.llmCycle=results[0].value;else console.warn("Gemini cycle refresh failed",results[0].reason);
  if(results[1].status==="fulfilled")state.llmStatus=results[1].value;else console.warn("Gemini status refresh failed",results[1].reason);
  if(results[2].status==="fulfilled")state.autoConsensus=results[2].value;else console.warn("Autonomous consensus refresh failed",results[2].reason);
  if(results[3].status==="fulfilled")state.policyObservations=results[3].value;else console.warn("Policy observation refresh failed",results[3].reason);
}
async function loadResponsiveness(){
  try{state.responsiveness=await api("/api/v1/atlas/scalping-responsiveness")}catch(e){console.warn("Responsiveness refresh failed",e)}
}
async function loadMarketCandles(){
  try{state.candles=await api("/api/v1/atlas/market-candles")}catch(e){console.warn("Market candle refresh failed",e)}
}
async function loadZoneMap(){
  try{state.zoneMap=await api("/api/v1/atlas/zone-map")}catch(e){console.warn("Zone map refresh failed",e)}
}
async function loadZonePlan(){
  try{state.zonePlan=await api("/api/v1/atlas/zone-execution-plan");state.zonePlanLoadedAt=Date.now()}catch(e){console.warn("Zone execution plan refresh failed",e)}
}
async function saveLlmCycleSchedule(){
  const interval=Number(document.getElementById("cycle-interval").value||240);
  const enabled=document.getElementById("cycle-enabled").checked;
  const execution_mode="AUTONOMOUS";
  const minimum_dwell_minutes=Number(document.getElementById("cycle-dwell").value||interval);
  const minimum_confidence=Number(document.getElementById("cycle-confidence").value||70);
  try{
    state.llmCycle=await api("/api/v1/atlas/llm/cycle-schedule",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({enabled,interval_minutes:interval,execution_mode,minimum_dwell_minutes,minimum_confidence})});
    renderAll();toast(enabled?`Event-driven Brain saved · ${interval}m health heartbeat enabled.`:"Event-driven Brain saved · health heartbeat disabled.");
  }catch(e){toast(e.message,true)}
}
async function runLlmCycleNow(){
  try{
    state.llmCycle=await jsonPost("/api/v1/atlas/llm/cycle-schedule/run-now",{});
    renderAll();toast(state.llmCycle.claimed?"Gemini policy analysis started.":pretty(state.llmCycle.reason),!state.llmCycle.claimed);
  }catch(e){toast(e.message,true)}
}
function reviewPayload(){
  const p=state.proposal;return {reviewer:"Nobel",note:"Atlas Operator Control Center",expected_runtime_fingerprint:p.runtime_fingerprint,expected_proposed_policy_epoch:p.proposed_policy_epoch}
}
async function requestReview(){try{await jsonPost(`/api/v1/atlas/advisory-proposals/${state.proposal.proposal_id}/request-review`,reviewPayload());await loadReview();renderAll();toast("Review requested.")}catch(e){toast(e.message,true)}}
async function approveCurrent(){try{await jsonPost(`/api/v1/atlas/advisory-proposals/${state.proposal.proposal_id}/approve`,reviewPayload());await loadReview();renderAll();toast("Proposal approved.")}catch(e){toast(e.message,true)}}
async function rejectCurrent(){try{await jsonPost(`/api/v1/atlas/advisory-proposals/${state.proposal.proposal_id}/reject`,reviewPayload());await loadReview();renderAll();toast("Proposal rejected.")}catch(e){toast(e.message,true)}}
async function buildSupervisedCommand(){
  const p=state.proposal, review=state.review?.approval||state.review||{};
  const hash=review.review_snapshot_hash||p.approval?.review_snapshot_hash;
  try{
    state.supervised=await jsonPost(`/api/v1/atlas/advisory-proposals/${p.proposal_id}/supervised-command-proposal`,{
      reviewer:"Nobel",note:"Atlas Operator Control Center command package",
      expected_runtime_fingerprint:p.runtime_fingerprint,expected_proposed_policy_epoch:p.proposed_policy_epoch,expected_review_snapshot_hash:hash
    });
    renderAll();go("control");toast("Supervised command package built.");
  }catch(e){toast(e.message,true)}
}
function pkg(){return state.supervised?.supervised_command_proposal||state.supervised}
async function loadArm(){
  try{state.arm=await api("/api/v1/atlas/supervised-execution-arm")}catch(e){console.warn(e)}
}
async function armExecution(){
  try{
    state.arm=await jsonPost("/api/v1/atlas/supervised-execution-arm",{
      actor:"Nobel",
      confirmation_phrase:"ARM_SUPERVISED_EXECUTION",
      minutes:30
    });
    renderAll();toast("Supervised execution armed for 30 minutes.");
  }catch(e){toast(e.message,true)}
}
async function disarmExecution(){
  try{
    state.arm=await jsonPost("/api/v1/atlas/supervised-execution-arm/disarm",{actor:"Nobel"});
    renderAll();toast("Supervised execution disarmed.");
  }catch(e){toast(e.message,true)}
}

async function runPreflight(){
  const p=pkg();if(!p)return;
  try{state.preflight=await api(`/api/v1/atlas/supervised-command-proposals/${p.supervised_command_id}/execution-preflight`);renderAll();toast((state.preflight.ready_for_supervised_execution??state.preflight.ready_for_explicit_demo_execution)?"Preflight passed.":"Preflight returned blockers.",!(state.preflight.ready_for_supervised_execution??state.preflight.ready_for_explicit_demo_execution))}
  catch(e){toast(e.message,true)}
}
function executePackage(){
  const p=pkg();if(!p)return;
  document.getElementById("modal-exec-summary").innerHTML=`Command <strong>${esc(text(p.command_preview?.hypothetical_command_version))}</strong> · Policy epoch <strong>${esc(text(p.command_preview?.target_policy_epoch))}</strong> · ${esc(text(p.command_preview?.runtime_control_count))} runtime controls.`;
  document.getElementById("confirm-modal").classList.add("show")
}
function closeModal(){document.getElementById("confirm-modal").classList.remove("show")}
async function confirmExecute(){
  const p=pkg();const s=p.source||{},ctx=p.current_context||{};
  try{
    state.execution=await jsonPost(`/api/v1/atlas/supervised-command-proposals/${p.supervised_command_id}/execute`,{
      actor:document.getElementById("modal-actor").value||"human_operator",
      note:"Atlas Operator Control Center execution",
      confirmation_phrase:"EXECUTE_SUPERVISED_COMMAND",
      allow_test_override_execution:Boolean(s.test_override_active),
      expected_source_proposal_id:s.proposal_id,
      expected_runtime_fingerprint:s.runtime_fingerprint,
      expected_target_policy_epoch:s.proposed_policy_epoch,
      expected_review_snapshot_hash:s.review_snapshot_hash,
      expected_baseline_command_version:ctx.baseline_command_version,
      expected_baseline_policy_epoch:ctx.baseline_policy_epoch
    });
    closeModal();
    await reconcileAuthoritativeState();
    renderAll();renderControls();toast("Policy execution completed. Atlas state refreshed; waiting for Nyao acknowledgement.");
  }catch(e){toast(e.message,true)}
}
function currentExecutionId(){
  if(state.execution?.execution_id)return state.execution.execution_id;
  const p=pkg();
  const event=(state.executionEvents?.events||[]).find(e=>e.supervised_command_id===p?.supervised_command_id&&["EXECUTED","EXECUTED_RECOVERED"].includes(e.action));
  return event?.execution_id||null;
}
async function reconcileAuthoritativeState(){
  await loadCore();
  await loadHistory();
  await loadProposal();
  await Promise.all([loadArm(),loadParameterIntelligence(),loadIntelligence(),loadResponsiveness(),loadMarketCandles(),loadZoneMap(),loadZonePlan()]);
}
async function refreshAck(){
  const executionId=currentExecutionId();if(!executionId)return;
  try{state.ack=await jsonPost(`/api/v1/atlas/supervised-executions/${executionId}/nyao-ack/refresh`,{});await reconcileAuthoritativeState();renderAll();renderControls();toast("Nyao acknowledgement: "+state.ack.state,badgeClass(state.ack.state)==="bad")}
  catch(e){toast(e.message,true)}
}

function renderHistory(){
  const a=state.audit||{};document.getElementById("h-audit").textContent=a.valid===true?"VALID":"—";document.getElementById("h-audit-count").textContent=a.checked_event_count==null?"—":`${a.checked_event_count} chained events`;
  const eps=state.epochs?.epochs||state.epochs?.policy_epochs||[];document.getElementById("h-epochs").textContent=Array.isArray(eps)?eps.length:text(state.epochs?.count);
  const outs=state.outcomes?.outcomes||state.outcomes?.closed||[];document.getElementById("h-outcomes").textContent=Array.isArray(outs)?outs.length:text(state.outcomes?.count);
  const events=state.executionEvents?.events||[];
  document.getElementById("execution-events").innerHTML=events.slice(0,16).map(e=>`<div class="event"><span class="muted">${esc((e.timestamp||"").replace("T"," ").slice(0,19))}</span><div><strong>${esc(pretty(e.action))}</strong><div class="muted mono">${esc(text(e.execution_id))}</div></div><span class="badge ${badgeClass(e.action)}">${esc(text(e.sequence))}</span></div>`).join("")||`<div class="callout">No execution events.</div>`;
  document.getElementById("policy-epochs").innerHTML=(Array.isArray(eps)?eps.slice(-12).reverse():[]).map(e=>`<div class="event"><span class="muted">${esc(text(e.created_at||e.registered_at||""))}</span><div><strong>Epoch ${esc(text(e.policy_epoch??e.epoch))}</strong><div class="muted">Command ${esc(text(e.applied_command_version??e.command_version))}</div></div><span class="badge info">${esc(text(e.runtime_control_count??157))}</span></div>`).join("")||`<div class="callout">No policy epochs returned.</div>`;
  document.getElementById("raw-diagnostics").textContent=JSON.stringify({audit:state.audit,latest_execution:events[0]||null,command:{command_version:state.command?.command_version,policy_epoch:state.command?.policy_epoch},status:{applied_command_version:state.status?.applied_command_version,policy_epoch:state.status?.policy_epoch}},null,2)
}
function accountMoney(v){const n=Number(v);return Number.isFinite(n)?`${n>=0?"+":"-"}$${Math.abs(n).toFixed(2)}`:"—"}
function renderAccountPerformance(){
  const a=state.accountPerf||{}, l=a.broker_ledger||{}, s=state.status||{};
  const by=(k)=>l[k]||{};
  const set=(id,v)=>{const e=document.getElementById(id);if(e)e.textContent=v};
  set("acct-today",accountMoney(by("today").realized_trading_pl));set("acct-yesterday",accountMoney(by("yesterday").realized_trading_pl));
  set("acct-week",accountMoney(by("last_7_days").realized_trading_pl));set("acct-month",accountMoney(by("last_30_days").realized_trading_pl));
  set("acct-balance",`$${Number(a.balance||0).toFixed(2)}`);set("acct-equity",`$${Number(a.equity||0).toFixed(2)} / ${accountMoney(a.floating_pl)}`);
  set("acct-deposits",`$${Number((l.lifetime||{}).deposits||0).toFixed(2)}`);set("acct-withdrawals",`$${Math.abs(Number((l.lifetime||{}).withdrawals||0)).toFixed(2)}`);
  const ms=String(s.market_session_state||"UNKNOWN");const b=document.getElementById("acct-market-state");if(b){b.textContent=`MARKET ${pretty(ms)}`;b.className=`badge ${ms==="OPEN"?"ok":ms==="CLOSING_SOON"?"warn":ms==="CLOSED"?"bad":"info"}`}
  const d=document.getElementById("acct-detail");if(d){const nc=Number(s.market_next_close_epoch||0), no=Number(s.market_next_open_epoch||0);d.textContent=l.version?`Broker server ledger · net deposits are separated from trading P/L.${ms==="OPEN"&&nc?` Next close ${new Date(nc*1000).toLocaleString()}.`:ms==="CLOSED"&&no?` Next open ${new Date(no*1000).toLocaleString()}.`:""}`:"Nyao account-ledger telemetry is unavailable. Recompile Nyao 44.6.0 for broker P/L and deposit history."}
}
async function resetConsensusWindow(){if(!confirm("Start a fresh Gemini consensus learning window? This does not change the active policy or close positions."))return;try{const r=await api("/api/v1/atlas/autonomous-policy-consensus/reset",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({actor:"human_operator",reason:"Operator reset from Atlas dashboard"})});state.autoConsensus=r.consensus||r;await loadLlmCycle();renderAll();toast("Learning window reset. Active policy unchanged.")}catch(e){toast(e.message,true)}}

function renderAll(){updateChrome();renderOverview();renderOpportunityQueue();renderDecisionTimeline();renderLiveAnalysis();renderAnalysis();renderPositions();renderLlmCycle();renderAutonomousConsensus();renderResponsiveness();renderAtlas();renderParameterIntelligence();renderAccountPerformance();renderHistory();const runtimeControls=document.getElementById("runtime-controls");if(runtimeControls&&!runtimeControls.children.length)renderControls()}

async function loadCore(){
  const before=`${state.command?.command_version??""}:${state.command?.policy_epoch??""}:${state.status?.applied_command_version??""}:${state.status?.policy_epoch??""}`;
  const [status,command]=await Promise.allSettled([api("/api/v1/nyao/status"),api("/api/v1/nyao/command")]);
  if(status.status==="fulfilled")state.status=status.value;
  if(command.status==="fulfilled")state.command=command.value;
  const after=`${state.command?.command_version??""}:${state.command?.policy_epoch??""}:${state.status?.applied_command_version??""}:${state.status?.policy_epoch??""}`;
  return before!==after;
}
async function loadIntelligence(){
  try{state.intelligence=await api("/api/v1/atlas/intelligence")}catch(e){console.warn("Intelligence refresh failed",e)}
}
async function loadParameterIntelligence(){
  try{state.parameterIntel=await api("/api/v1/atlas/parameter-intelligence")}catch(e){console.warn("Parameter intelligence refresh failed",e)}
}
async function loadProposal(){
  try{const d=await api("/api/v1/atlas/advisory-proposal");state.proposal=d.proposal||d;await Promise.all([loadReview(),loadSupervised()])}catch(e){console.warn(e)}
}
async function loadHistory(){
  const rs=await Promise.allSettled([
    api("/api/v1/atlas/supervised-execution-events?limit=100"),
    api("/api/v1/atlas/supervised-execution-events/verify"),
    api("/api/v1/atlas/policy-epochs?limit=100"),
    api("/api/v1/atlas/outcomes?closed_limit=100&include_active=true"),
    api("/api/v1/atlas/policy-performance"),
    api("/api/v1/atlas/autonomous-policy-applications?limit=50"),
    api("/api/v1/atlas/risk-units"),
    api("/api/v1/atlas/recovery-attribution"),
    api("/api/v1/atlas/recovery-risk"),
    api("/api/v1/atlas/account-performance"),
    api("/api/v1/atlas/brain-events")
  ]);
  if(rs[0].status==="fulfilled")state.executionEvents=rs[0].value;
  if(rs[1].status==="fulfilled")state.audit=rs[1].value;
  if(rs[2].status==="fulfilled")state.epochs=rs[2].value;
  if(rs[3].status==="fulfilled")state.outcomes=rs[3].value;
  if(rs[4].status==="fulfilled")state.performance=rs[4].value;
  if(rs[5].status==="fulfilled")state.autoApplications=rs[5].value;
  if(rs[6].status==="fulfilled")state.riskUnits=rs[6].value;
  if(rs[7].status==="fulfilled")state.recoveryAttribution=rs[7].value;
  if(rs[8].status==="fulfilled")state.recoveryRisk=rs[8].value;
  if(rs[9].status==="fulfilled")state.accountPerf=rs[9].value;
  if(rs[10].status==="fulfilled")state.brainEvents=rs[10].value;
}
async function boot(){
  // Restore operator notification preferences before the first live render.
  // The controls persist in browser localStorage and must survive refreshes.
  loadNotificationSettings();
  try{
    await loadSymbols();
    await loadCore();
    await loadRiskAppetite();
    await loadIntelligence();
    await loadParameterIntelligence();
    await loadArm();
    await loadLlmCycle();
    await loadResponsiveness();
    await loadMarketCandles();
    await Promise.all([loadZoneMap(),loadZonePlan()]);
    await loadProposal();
    await loadHistory();
    renderAll();
    renderControls();
    // Establish decision history baseline only after all authoritative state is loaded.
    state.decisionBaseline=decisionSnapshot();
  }catch(e){toast(e.message,true)}

  setInterval(async()=>{const changed=await loadCore();await loadArm();if(changed){await loadHistory();await loadProposal()}renderAll();evaluateNotifications();evaluateDecisionTimeline()},2000);
  setInterval(async()=>{await loadIntelligence();renderAll()},5000);
  setInterval(async()=>{await loadLlmCycle();renderAll();evaluateDecisionTimeline()},5000);
  setInterval(async()=>{await loadResponsiveness();renderAll()},15000);
  setInterval(async()=>{await loadMarketCandles();renderAll()},15000);
  setInterval(async()=>{await loadZoneMap();renderAll()},15000);
  setInterval(async()=>{await loadZonePlan();renderAll();evaluateDecisionTimeline()},5000);
  setInterval(async()=>{await loadParameterIntelligence();renderAll()},10000);
  setInterval(async()=>{await loadSymbols();await loadProposal();renderAll()},10000);
  setInterval(async()=>{await loadHistory();renderAll();evaluateDecisionTimeline()},15000);

}
boot();
