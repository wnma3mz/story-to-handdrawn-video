import rawUploadedStoryboard from '@uploaded-storyboard-data';
import {parseStoryboard, totalFramesFor} from './storyboard';

export const uploadedStoryboard = parseStoryboard(
  rawUploadedStoryboard,
  'Uploaded storyboard',
);
export const uploadedTotalFrames = totalFramesFor(uploadedStoryboard);
