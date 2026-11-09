import test from 'node:test';
import assert from 'node:assert/strict';
import {applyAnnouncementReview,ANNOUNCEMENT_REVIEWS} from './reverse-split-live/announcement-reviews.mjs';
test('a reviewed cover and logo supplement only their exact original PDF and exact flagged pages',()=>{
 const digest=Object.keys(ANNOUNCEMENT_REVIEWS)[0],source={schema:'announcement_text.v1',complete:false,pages:29,review_pages:[1,28],text:'Native readable pages',ocr_candidates:[{page:1,text:'UNVERIFIED OCR'}]};
 const reviewed=applyAnnouncementReview(source,digest);assert.equal(reviewed.complete,true);assert.equal(reviewed.OCR_admitted_to_signals,false);assert.ok(reviewed.text.startsWith(source.text));assert.match(reviewed.text,/GLAUKOS/);assert.ok(!reviewed.text.includes('UNVERIFIED OCR'));assert.equal(source.complete,false);
 for(const [input,sha] of [[source,'0'.repeat(64)],[{...source,pages:30},digest],[{...source,review_pages:[1,27]},digest]])assert.equal(applyAnnouncementReview(input,sha).complete,false);
});
