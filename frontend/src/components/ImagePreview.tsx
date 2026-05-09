import { X } from 'lucide-react';

// ---------------------------------------------------------------------------
// ImagePreview — Round 15 / PR #24
// ---------------------------------------------------------------------------

export interface ImagePreviewProps {
  src: string;
  alt?: string;
  onRemove?: () => void;
}

/**
 * ImagePreview renders an image in an aspect-fit, rounded container with
 * an optional small "remove" (×) button overlaid in the top-right corner.
 *
 * Used by CapturePage to show the user the image they just selected before
 * they confirm with "Save image note".
 */
export function ImagePreview({
  src,
  alt = 'Image preview',
  onRemove,
}: ImagePreviewProps): React.ReactElement {
  return (
    <div className="relative inline-block max-w-full overflow-hidden rounded-xl border border-slate-700 bg-slate-900">
      <img
        src={src}
        alt={alt}
        className="block max-h-96 w-full object-contain"
      />
      {onRemove ? (
        <button
          type="button"
          onClick={onRemove}
          aria-label="Remove image"
          className="absolute right-2 top-2 flex h-8 w-8 items-center justify-center rounded-full bg-slate-900/80 text-slate-100 backdrop-blur transition-colors hover:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-400"
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      ) : null}
    </div>
  );
}

export default ImagePreview;
