import{R as f,ag as y,W as m,s as q,F as w}from"./index.6e58b9bb.js";const o=[];function z(e,u){return{subscribe:A(e,u).subscribe}}function A(e,u=f){let r;const n=new Set;function a(t){if(q(e,t)&&(e=t,r)){const i=!o.length;for(const s of n)s[1](),o.push(s,e);if(i){for(let s=0;s<o.length;s+=2)o[s][0](o[s+1]);o.length=0}}}function l(t){a(t(e))}function b(t,i=f){const s=[t,i];return n.add(s),n.size===1&&(r=u(a)||f),t(e),()=>{n.delete(s),n.size===0&&r&&(r(),r=null)}}return{set:a,update:l,subscribe:b}}function F(e,u,r){const n=!Array.isArray(e),a=n?[e]:e,l=u.length<2;return z(r,b=>{let t=!1;const i=[];let s=0,d=f;const g=()=>{if(s)return;d();const c=u(n?i[0]:i,b);l?b(c):d=w(c)?c:f},_=a.map((c,p)=>y(c,h=>{i[p]=h,s&=~(1<<p),t&&g()},()=>{s|=1<<p}));return t=!0,g(),function(){m(_),d(),t=!1}})}export{F as d,A as w};
