// Narrow visual supplements: never an automatic acceptance of OCR candidates.
export const ANNOUNCEMENT_REVIEWS=Object.freeze({
 '861859d044e64437564b63daf325a93a41a6623f26752cfa7db96e55829f93c9':{
  schema:'announcement_visual_review.v1',reviewed_at:'2026-11-09T17:55:00Z',reviewer:'Codex visual inspection of rendered original pages',source_url:'https://www.sec.gov/Archives/edgar/data/1192448/000119312526450710/gkos-ex99_1.pdf',source_sha256:'861859d044e64437564b63daf325a93a41a6623f26752cfa7db96e55829f93c9',pages:29,
  supplements:[{page:1,text:'GLAUKOS. TRANSFORMING VISION. Investor Presentation. NOVEMBER 2026.',basis:'Cover with issuer logo, presentation title and month; visually read in full.'},{page:28,text:'GLAUKOS. TRANSFORMING VISION.',basis:'Issuer logo and tagline on a blank white page; visually read in full.'}],
  scope:'Only the two flagged pages in this exact PDF. Remaining pages retain the native extraction. No OCR candidate is accepted, and no financial value or announcement decision is supplied by this review.'
 }
});
export function applyAnnouncementReview(result,digest){
 const review=ANNOUNCEMENT_REVIEWS[digest];if(!review||result.schema!=='announcement_text.v1'||result.complete||result.pages!==review.pages||!Array.isArray(result.review_pages)||result.review_pages.join(',')!==review.supplements.map(p=>p.page).join(','))return result;
 return {...result,complete:true,text:result.text+'\n\n'+review.supplements.map(p=>'[Visually verified page '+p.page+']\n'+p.text).join('\n\n'),visual_review:review,OCR_admitted_to_signals:false};
}
