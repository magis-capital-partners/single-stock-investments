// Narrow visual supplements: never an automatic acceptance of OCR candidates.
export const ANNOUNCEMENT_REVIEWS=Object.freeze({
 'dd27b1c42187bdd34bff426f8cda5f8af7f50696aaf48d47a2cc9a5b82316a34':{
  schema:'announcement_visual_review.v1',reviewed_at:'2026-11-20T15:45:00Z',reviewer:'Codex visual inspection of all seven rendered original divider pages',source_url:'https://www.sec.gov/Archives/edgar/data/1920294/000119312526467904/rzlv-ex99_1.pdf',source_sha256:'dd27b1c42187bdd34bff426f8cda5f8af7f50696aaf48d47a2cc9a5b82316a34',pages:45,
  supplements:[4,9,13,23,29,33,41].map((page,index)=>({page,text:'SECTION '+String(index+1).padStart(2,'0'),basis:'Rendered original section divider: section number, the already extracted native heading, issuer logo and decorative blue background. No additional financial facts or corporate-action terms.'})),
  scope:'Only these seven section dividers in this exact 45-page PDF. Native headings and all other pages retain their original extraction. No OCR candidate, financial value or announcement decision is supplied by this review.'
 },
 '861859d044e64437564b63daf325a93a41a6623f26752cfa7db96e55829f93c9':{
  schema:'announcement_visual_review.v1',reviewed_at:'2026-11-09T17:55:00Z',reviewer:'Codex visual inspection of rendered original pages',source_url:'https://www.sec.gov/Archives/edgar/data/1192448/000119312526450710/gkos-ex99_1.pdf',source_sha256:'861859d044e64437564b63daf325a93a41a6623f26752cfa7db96e55829f93c9',pages:29,
  supplements:[{page:1,text:'GLAUKOS. TRANSFORMING VISION. Investor Presentation. NOVEMBER 2026.',basis:'Cover with issuer logo, presentation title and month; visually read in full.'},{page:28,text:'GLAUKOS. TRANSFORMING VISION.',basis:'Issuer logo and tagline on a blank white page; visually read in full.'}],
  scope:'Only the two flagged pages in this exact PDF. Remaining pages retain the native extraction. No OCR candidate is accepted, and no financial value or announcement decision is supplied by this review.'
 },
 '980d0a7a91a078f64e4e9c80c0108ffccd18bbccf404d64bfa3f1f27f9baba60':{
  schema:'announcement_visual_review.v1',reviewed_at:'2026-11-10T16:52:39Z',reviewer:'Codex visual inspection of rendered original page',source_url:'https://www.sec.gov/Archives/edgar/data/1015820/000101582024000069/exhibit9972023ifrsrpt.pdf',source_sha256:'980d0a7a91a078f64e4e9c80c0108ffccd18bbccf404d64bfa3f1f27f9baba60',pages:372,
  supplements:[{page:1,text:'Exhibit 99.7. QIAGEN N.V. IFRS Annual Report 2023. QIAGEN.',basis:'Rendered original cover: issuer, report title, year and logos; background photograph of laboratory equipment and a technician. No financial values or reverse-split terms are supplied.'}],
  scope:'Only the cover in this exact PDF. All remaining pages retain native text extraction; no OCR candidate, financial value or announcement decision is supplied by this review.'
 }
});
export function applyAnnouncementReview(result,digest){
 const review=ANNOUNCEMENT_REVIEWS[digest];if(!review||result.schema!=='announcement_text.v1'||result.complete||result.pages!==review.pages||!Array.isArray(result.review_pages)||result.review_pages.join(',')!==review.supplements.map(p=>p.page).join(','))return result;
 return {...result,complete:true,text:result.text+'\n\n'+review.supplements.map(p=>'[Visually verified page '+p.page+']\n'+p.text).join('\n\n'),visual_review:review,OCR_admitted_to_signals:false};
}
