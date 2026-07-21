import {Composition} from 'remotion';
import {StoryVideo} from './StoryVideo';
import {storyboard, totalFrames} from './storyboard';
import {UploadedStoryVideo} from './UploadedStoryVideo';
import {
  uploadedStoryboard,
  uploadedTotalFrames,
} from './uploadedStoryboard';

export const RemotionRoot: React.FC = () => {
  const {project} = storyboard;

  return (
    <>
      <Composition
        id="PictureSilent"
        component={StoryVideo}
        durationInFrames={totalFrames}
        fps={project.fps}
        width={project.width}
        height={project.height}
        defaultProps={{}}
      />
      <Composition
        id="UploadedPictureSilent"
        component={UploadedStoryVideo}
        durationInFrames={uploadedTotalFrames}
        fps={uploadedStoryboard.project.fps}
        width={uploadedStoryboard.project.width}
        height={uploadedStoryboard.project.height}
        defaultProps={{}}
      />
    </>
  );
};
