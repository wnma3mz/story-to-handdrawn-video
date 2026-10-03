import {Composition} from 'remotion';
import {MotionGraphicsVideo} from './compositions/motiongraphics/MotionGraphicsVideo';
import {EpisodeCover} from './EpisodeCover';
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
      {/* handdrawn：AI 生图 + 代码动效，上游内容层的默认成片路径 */}
      <Composition
        id="PictureSilent"
        component={StoryVideo}
        durationInFrames={totalFrames}
        fps={project.fps}
        width={project.width}
        height={project.height}
        defaultProps={{}}
      />
      {/* motiongraphics：纯代码绘制，不经过出图环节 */}
      <Composition
        id="MotionGraphicsSilent"
        component={MotionGraphicsVideo}
        durationInFrames={totalFrames}
        fps={project.fps}
        width={project.width}
        height={project.height}
        defaultProps={{value: storyboard}}
      />
      <Composition
        id="EpisodeCover"
        component={EpisodeCover}
        durationInFrames={1}
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
