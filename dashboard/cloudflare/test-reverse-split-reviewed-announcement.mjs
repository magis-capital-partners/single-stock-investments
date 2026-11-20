import test from 'node:test';
import assert from 'node:assert/strict';
import {applyAnnouncementReview,ANNOUNCEMENT_REVIEWS} from './reverse-split-live/announcement-reviews.mjs';
test('the exact Rezolve divider pages can be reviewed without admitting OCR or financial values',()=>{
 const digest='dd27b1c42187bdd34bff426f8cda5f8af7f50696aaf48d47a2cc9a5b82316a34',source={schema:'announcement_text.v1',complete:false,pages:45,review_pages:[4,9,13,23,29,33,41],text:'Native presentation text and headings',ocr_candidates:[{page:4,text:'UNVERIFIED OCR'}]};
 const result=applyAnnouncementReview(source,digest);assert.equal(result.complete,true);assert.equal(result.OCR_admitted_to_signals,false);assert.ok(!result.text.includes('UNVERIFIED OCR'));assert.equal(result.visual_review.supplements.length,7);
 for(const input of [{...source,pages:46},{...source,review_pages:[4,9,13,23,29,33,40]}])assert.equal(applyAnnouncementReview(input,digest).complete,false);
 assert.equal(applyAnnouncementReview(source,'0'.repeat(64)).complete,false);
});
test('a reviewed cover and logo supplement only their exact original PDF and exact flagged pages',()=>{
 const digest='861859d044e64437564b63daf325a93a41a6623f26752cfa7db96e55829f93c9',source={schema:'announcement_text.v1',complete:false,pages:29,review_pages:[1,28],text:'Native readable pages',ocr_candidates:[{page:1,text:'UNVERIFIED OCR'}]};
 const reviewed=applyAnnouncementReview(source,digest);assert.equal(reviewed.complete,true);assert.equal(reviewed.OCR_admitted_to_signals,false);assert.ok(reviewed.text.startsWith(source.text));assert.match(reviewed.text,/GLAUKOS/);assert.ok(!reviewed.text.includes('UNVERIFIED OCR'));assert.equal(source.complete,false);
 for(const [input,sha] of [[source,'0'.repeat(64)],[{...source,pages:30},digest],[{...source,review_pages:[1,27]},digest]])assert.equal(applyAnnouncementReview(input,sha).complete,false);
});
