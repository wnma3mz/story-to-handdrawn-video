import rawUploadedStoryboard from '../storyboard.uploaded.json';
import {totalFramesFor} from './storyboard';
import type {Storyboard} from './types';

export const uploadedStoryboard = rawUploadedStoryboard as Storyboard;
export const uploadedTotalFrames = totalFramesFor(uploadedStoryboard);
