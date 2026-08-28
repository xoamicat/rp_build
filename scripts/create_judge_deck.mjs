import fs from "node:fs/promises";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const OUT = "C:/Users/vansh/OneDrive/Desktop/rp_build/SettleX_Atlas_Judge_Deck.pptx";
const PREVIEW = "C:/Users/vansh/OneDrive/Desktop/rp_build/tmp/atlas-deck";
const W = 1280, H = 720;
const C = { navy: "#082C5C", blue: "#075985", sky: "#EAF6FF", cyan: "#06B6D4", ink: "#10243E", muted: "#52657E", line: "#C8DDF0", white: "#FFFFFF", green: "#047857", amber: "#A16207" };

async function save(blob, file) { await fs.writeFile(file, new Uint8Array(await blob.arrayBuffer())); }
function add(slide, {x, y, w, h, text = "", fill = "none", line = "none", color = C.ink, size = 20, bold = false, radius = "rounded-xl", name = "shape", align = "left"}) {
  const sh = slide.shapes.add({
    geometry: text && fill === "none" ? "textbox" : "roundRect", name,
    position: {left: x, top: y, width: w, height: h}, fill,
    line: {style: "solid", fill: line === "none" ? "none" : line, width: line === "none" ? 0 : 1},
    borderRadius: radius,
  });
  if (text) { sh.text = text; sh.text.style = {fontSize: size, bold, color, alignment: align}; }
  return sh;
}
function footer(slide, n) {
  add(slide, {x: 72, y: 678, w: 700, h: 18, text: "SETTLEX ATLAS  •  RAZORPAY BUILDATHON 2026  •  OPEN INNOVATION", color: "#7B91AA", size: 11, bold: true, name: "footer"});
  add(slide, {x: 1160, y: 678, w: 48, h: 18, text: String(n).padStart(2, "0"), color: "#7B91AA", size: 11, bold: true, align: "right", name: "page"});
}
function title(slide, eyebrow, headline, sub) {
  add(slide, {x:72,y:52,w:930,h:22,text:eyebrow.toUpperCase(),color:C.blue,size:13,bold:true,name:"eyebrow"});
  add(slide, {x:72,y:88,w:1120,h:72,text:headline,color:C.ink,size:42,bold:true,name:"headline"});
  if (sub) add(slide, {x:72,y:170,w:1010,h:50,text:sub,color:C.muted,size:20,name:"subtitle"});
}
function dot(slide, x, y, color) { add(slide, {x, y, w:12, h:12, fill:color, line:"none", radius:"rounded-full", name:"dot"}); }
function note(slide, text) { slide.speakerNotes.textFrame.setText(text); slide.speakerNotes.setVisible(true); }

async function main() {
  await fs.mkdir(PREVIEW, {recursive:true});
  const p = Presentation.create({slideSize:{width:W,height:H}});

  // 1 — open on the human cost, not the technology.
  {
    const s = p.slides.add(); s.background.fill = C.sky;
    add(s,{x:0,y:0,w:W,h:H,fill:C.navy,line:"none",radius:"rounded-none",name:"navy-field"});
    add(s,{x:72,y:66,w:430,h:20,text:"RAZORPAY BUILDATHON 2026  •  TRACK 5",color:"#7DD3FC",size:14,bold:true,name:"eyebrow"});
    add(s,{x:72,y:125,w:700,h:180,text:"The payment was valid.\nThe promise changed.",color:C.white,size:54,bold:true,name:"headline"});
    add(s,{x:72,y:330,w:610,h:90,text:"SettleX Atlas preserves the exact offer an AI buyer saw—and stops a silent change before fulfilment or renewal.",color:"#D7ECFF",size:24,name:"subtitle"});
    add(s,{x:830,y:122,w:310,h:360,fill:C.white,line:"#6FB9EA",radius:"rounded-2xl",name:"offer-card"});
    add(s,{x:866,y:166,w:230,h:19,text:"BUYER-APPROVED OFFER",color:C.blue,size:13,bold:true,name:"card-label"});
    add(s,{x:866,y:210,w:230,h:48,text:"2 × Margherita\n₹680 • Saturday",color:C.ink,size:24,bold:true,name:"card-terms"});
    add(s,{x:866,y:302,w:228,h:1,fill:"#D8E9F6",line:"none",radius:"rounded-none",name:"divider"});
    add(s,{x:866,y:335,w:230,h:52,text:"Later: price ↑, item added, delivery delayed",color:C.amber,size:18,bold:true,name:"drift"});
    add(s,{x:866,y:420,w:228,h:34,text:"ATLAS → RECONFIRM",color:C.green,size:19,bold:true,name:"outcome"});
    dot(s, 98, 514, C.cyan); add(s,{x:122,y:504,w:535,h:30,text:"Payment rails stay with Razorpay. The commercial promise gets a witness.",color:"#B9DBF7",size:17,name:"bottom"});
    note(s,"[Sources]\n- Product framing and implemented behavior: SettleX Atlas repository, SUBMISSION.md and GAP_ANALYSIS.md.\n- No external statistic is claimed on this slide.");
  }

  // 2 — make the problem precise.
  {
    const s=p.slides.add(); s.background.fill=C.white; title(s,"THE UNSOLVED MOMENT","Authorisation is not proof of the full commercial promise.","In an agentic journey, the buyer may approve a dynamic offer before the merchant’s catalogue or fulfilment system changes.");
    const x=[72,432,792]; const texts=[
      ["Buyer sees","SKU · price · delivery\nreturns · substitutions\nrenewal terms"],
      ["Payment succeeds","Razorpay authorises\nand records money\nmovement"],
      ["Fulfilment changes","New catalogue or OMS\nterms can silently\ndiverge later"],
    ];
    for(let i=0;i<3;i++){ add(s,{x:x[i],y:286,w:300,h:230,fill:i===2?"#FFF7E6":"#F4FAFF",line:i===2?"#F5CB7A":C.line,radius:"rounded-2xl",name:`problem-${i}`}); add(s,{x:x[i]+28,y:320,w:230,h:28,text:`0${i+1}  ${texts[i][0].toUpperCase()}`,color:i===2?C.amber:C.blue,size:14,bold:true,name:`step-${i}`}); add(s,{x:x[i]+28,y:370,w:236,h:100,text:texts[i][1],color:C.ink,size:23,bold:true,name:`copy-${i}`}); }
    add(s,{x:72,y:560,w:1020,h:40,text:"The gap is post-consent commercial drift—not fraud scoring, checkout replacement, or generic reconciliation.",color:C.navy,size:23,bold:true,name:"thesis"}); footer(s,2);
    note(s,"[Sources]\n- Gap hypothesis: GAP_ANALYSIS.md, based on publicly documented Razorpay Agent Studio, Orders, webhooks and Settlement Recon surfaces.\n- No adoption or loss-rate statistic is claimed.");
  }

  // 3 — show the new primitive.
  {
    const s=p.slides.add(); s.background.fill=C.sky; title(s,"THE PRODUCT","Atlas freezes the promise, then compares it before the next irreversible action.","The final decision is a deterministic field-level diff—not an opaque AI score.");
    const nodes=[]; const labels=["Render\nbuyer-visible offer","Sign canonical\nOffer Lock","Create ordinary\nRazorpay Order","Before fulfilment:\nALLOW · RECONFIRM · ESCALATE"]; const xs=[72,350,628,906];
    for(let i=0;i<4;i++){ const n=add(s,{x:xs[i],y:315,w:220,h:150,fill:C.white,line:C.line,radius:"rounded-2xl",name:`flow-${i}`}); nodes.push(n); }
    for(let i=0;i<3;i++) s.shapes.connect(nodes[i],nodes[i+1],{kind:"straight",fromSide:"right",toSide:"left",line:{style:"solid",fill:"#4A98CE",width:3},head:{type:"arrow",width:"med",length:"med"}});
    for(let i=0;i<4;i++){ add(s,{x:xs[i]+24,y:342,w:170,h:22,text:`0${i+1}`,color:C.cyan,size:14,bold:true,name:`flow-num-${i}`}); add(s,{x:xs[i]+24,y:382,w:175,h:64,text:labels[i],color:C.ink,size:20,bold:true,name:`flow-text-${i}`}); }
    add(s,{x:72,y:545,w:1136,h:63,fill:"#E7F8F4",line:"#A7E5D3",radius:"rounded-xl",name:"rule"}); add(s,{x:96,y:564,w:1084,h:25,text:"Seller/currency identity change → ESCALATE. Higher price, added item, later delivery or changed policy → RECONFIRM.",color:C.green,size:19,bold:true,name:"rule-text"}); footer(s,3);
    note(s,"[Sources]\n- Implemented drift policy: sakshi/offer_lock.py and tests/test_offer_lock.py.\n- Razorpay Orders notes limits: Razorpay Orders API documentation, linked in INTEGRATION.md.");
  }

  // 4 — integration truth.
  {
    const s=p.slides.add(); s.background.fill=C.white; title(s,"INTEGRATION","Atlas fits between systems merchants already use.","It does not collect credentials, replace checkout, or take over fulfilment.");
    const a=add(s,{x:95,y:292,w:230,h:135,fill:"#EFF8FF",line:C.line,radius:"rounded-2xl",name:"agent"}); const b=add(s,{x:446,y:292,w:230,h:135,fill:"#EAF6FF",line:"#7CC8F3",radius:"rounded-2xl",name:"atlas"}); const c=add(s,{x:797,y:235,w:220,h:115,fill:"#F4FAFF",line:C.line,radius:"rounded-2xl",name:"razorpay"}); const d=add(s,{x:797,y:400,w:220,h:115,fill:"#FFF7E6",line:"#F5CB7A",radius:"rounded-2xl",name:"oms"});
    s.shapes.connect(a,b,{kind:"straight",fromSide:"right",toSide:"left",line:{style:"solid",fill:"#4A98CE",width:3},head:{type:"arrow",width:"med",length:"med"}}); s.shapes.connect(b,c,{kind:"elbow",fromSide:"right",toSide:"left",line:{style:"solid",fill:"#4A98CE",width:3},head:{type:"arrow",width:"med",length:"med"}}); s.shapes.connect(b,d,{kind:"elbow",fromSide:"right",toSide:"left",line:{style:"solid",fill:"#4A98CE",width:3},head:{type:"arrow",width:"med",length:"med"}});
    add(s,{x:120,y:322,w:180,h:53,text:"Buyer agent\nor merchant chat",color:C.ink,size:21,bold:true,name:"agent-text"}); add(s,{x:470,y:316,w:180,h:55,text:"SettleX Atlas\nOffer Lock",color:C.navy,size:22,bold:true,name:"atlas-text"}); add(s,{x:823,y:260,w:170,h:55,text:"Razorpay\nOrder + webhooks",color:C.ink,size:20,bold:true,name:"rzp-text"}); add(s,{x:823,y:425,w:170,h:55,text:"OMS / renewal\n/ support queue",color:C.ink,size:20,bold:true,name:"oms-text"});
    add(s,{x:95,y:555,w:1020,h:35,text:"INPUT: structured offer + opaque approval ref  •  OUTPUT: signed proof + order notes + field-level decision",color:C.blue,size:20,bold:true,name:"io"}); footer(s,4);
    note(s,"[Sources]\n- Integration contract: INTEGRATION.md.\n- Razorpay Orders API and payment webhooks documentation, linked there.\n- Architecture is an implementation proposal; no private Razorpay feature is asserted.");
  }

  // 5 — agentic AI bar and safety proof.
  {
    const s=p.slides.add(); s.background.fill=C.sky; title(s,"MEANINGFUL AI, BOUNDED AT THE MONEY EDGE","AI drafts; deterministic code decides; the buyer consents.","That separation makes the AI useful without letting it invent commercial truth or execute money movement.");
    const y=[286,390,494]; const labels=["AI may","Code enforces","Buyer / operations decide"]; const details=["Translate natural language → known catalogue SKU + quantity; surface uncertainty.","Server hydrates price, delivery and policy. Unknown SKUs fail closed. Drift verdict is deterministic.","Explicitly sign the offer. Reconfirm on material change. Escalate identity changes to a human."];
    for(let i=0;i<3;i++){ add(s,{x:72,y:y[i],w:1136,h:76,fill:C.white,line:C.line,radius:"rounded-xl",name:`guard-${i}`}); add(s,{x:98,y:y[i]+21,w:260,h:28,text:labels[i],color:i===0?"#6D28D9":i===1?C.blue:C.green,size:20,bold:true,name:`guard-label-${i}`}); add(s,{x:388,y:y[i]+20,w:770,h:36,text:details[i],color:C.ink,size:18,name:`guard-detail-${i}`}); }
    footer(s,5); note(s,"[Sources]\n- Bounded composer: sakshi/offer_composer.py, sakshi/offer_lock.py, tests/test_offer_composer.py.\n- Model provenance and no-consent boundary: VALIDATION.md.");
  }

  // 6 — credible close, with proof and honest ask.
  {
    const s=p.slides.add(); s.background.fill=C.navy; add(s,{x:72,y:52,w:1050,h:22,text:"WHY THIS IS READY FOR A REAL PILOT",color:"#7DD3FC",size:13,bold:true,name:"eyebrow"}); add(s,{x:72,y:92,w:1080,h:64,text:"The demo proves the control. The pilot proves the value.",color:C.white,size:42,bold:true,name:"headline"});
    const cards=[
      ["95 automated checks","Signature, notes capacity, bounded AI, route handling, durable store and webhook adapter."],
      ["Real Test Mode order artifact","Official SDK created and fetched an unpaid order carrying all 15 permitted note fields."],
      ["Durable local evidence","Signed Offer Lock survived an actual server restart; no raw buyer text in notes."],
    ]; const cx=[72,443,814];
    for(let i=0;i<3;i++){ add(s,{x:cx[i],y:246,w:322,h:205,fill:"#123E73",line:"#2F6FA6",radius:"rounded-2xl",name:`proof-${i}`}); add(s,{x:cx[i]+24,y:276,w:270,h:50,text:cards[i][0],color:C.white,size:23,bold:true,name:`proof-title-${i}`}); add(s,{x:cx[i]+24,y:345,w:270,h:68,text:cards[i][1],color:"#CFE6FA",size:16,name:`proof-body-${i}`}); }
    add(s,{x:72,y:520,w:1136,h:88,fill:"#E7F8F4",line:"#A7E5D3",radius:"rounded-2xl",name:"ask"}); add(s,{x:100,y:544,w:1025,h:25,text:"Pilot ask: shadow one high-drift merchant flow for 30 days—substitution, delivery change or renewal.",color:C.green,size:20,bold:true,name:"ask-title"}); add(s,{x:100,y:575,w:1035,h:20,text:"Measure silent drift caught, reviewer agreement, evidence completeness and time-to-resolution before enabling a reconfirmation gate.",color:C.ink,size:16,name:"ask-body"}); footer(s,6);
    note(s,"[Sources]\n- 95 checks: local pytest suite at deck creation time.\n- Test Mode artifact: data/evidence/razorpay-test-mode-atlas_verify_1787943567.json.\n- Durable restart proof and pilot design: VALIDATION.md and PILOT_PLAN.md.\n- External Razorpay payment capture is not claimed; WEBHOOK_REHEARSAL.md records the remaining public-HTTPS step.");
  }

  for (const [i, slide] of p.slides.items.entries()) await save(await p.export({slide,format:"png",scale:1}), `${PREVIEW}/slide-${i+1}.png`);
  await save(await p.export({format:"webp",montage:true,scale:1}), `${PREVIEW}/montage.webp`);
  const pptx = await PresentationFile.exportPptx(p); await pptx.save(OUT);
}
main().catch(err => { console.error(err); process.exitCode = 1; });
