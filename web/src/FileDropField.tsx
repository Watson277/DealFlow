import {
  type ChangeEvent,
  type DragEvent,
  type KeyboardEvent,
  useId,
  useRef,
  useState,
} from "react";
import { FileCheck2, UploadCloud } from "lucide-react";

const DEFAULT_MAX_BYTES = 50 * 1024 * 1024;

type FileDropFieldProps = {
  id: string;
  title: string;
  help: string;
  accept: string;
  allowedExtensions: string[];
  maxBytes?: number;
};

function formatFileSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.ceil(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function FileDropField({
  id,
  title,
  help,
  accept,
  allowedExtensions,
  maxBytes = DEFAULT_MAX_BYTES,
}: FileDropFieldProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const dragDepth = useRef(0);
  const helpId = useId();
  const errorId = useId();
  const [dragging, setDragging] = useState(false);
  const [selected, setSelected] = useState<File | null>(null);
  const [error, setError] = useState("");

  const clearInput = () => {
    if (inputRef.current) inputRef.current.value = "";
    setSelected(null);
  };

  const validate = (file: File) => {
    const lowerName = file.name.toLowerCase();
    if (!allowedExtensions.some((extension) => lowerName.endsWith(extension))) {
      return `不支持 ${file.name}，请选择 ${allowedExtensions.join("、")} 文件`;
    }
    if (file.size > maxBytes) {
      return `文件不能超过 ${formatFileSize(maxBytes)}`;
    }
    return "";
  };

  const useFile = (file: File, files?: FileList) => {
    const validationError = validate(file);
    if (validationError) {
      clearInput();
      setError(validationError);
      return;
    }
    if (files && inputRef.current) inputRef.current.files = files;
    setSelected(file);
    setError("");
  };

  const onChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.currentTarget.files?.[0];
    if (!file) {
      setSelected(null);
      setError("");
      return;
    }
    useFile(file);
  };

  const onDragEnter = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    dragDepth.current += 1;
    setDragging(true);
  };

  const onDragLeave = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    dragDepth.current = Math.max(0, dragDepth.current - 1);
    if (dragDepth.current === 0) setDragging(false);
  };

  const onDrop = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    dragDepth.current = 0;
    setDragging(false);
    if (event.dataTransfer.files.length !== 1) {
      clearInput();
      setError("一次只能上传一个文件");
      return;
    }
    const file = event.dataTransfer.files[0];
    useFile(file, event.dataTransfer.files);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLLabelElement>) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      inputRef.current?.click();
    }
  };

  return (
    <label
      className={`file-field${dragging ? " drag-active" : ""}${error ? " invalid" : ""}`}
      data-testid={`${id}-drop-zone`}
      role="button"
      tabIndex={0}
      onKeyDown={onKeyDown}
      onDragEnter={onDragEnter}
      onDragOver={(event) => event.preventDefault()}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
    >
      {selected ? <FileCheck2 aria-hidden="true" /> : <UploadCloud aria-hidden="true" />}
      <strong>{selected ? selected.name : title}</strong>
      <span id={helpId}>
        {selected
          ? `${formatFileSize(selected.size)} · 点击或拖入其他文件可替换`
          : `拖动文件到此处，或点击选择。${help}`}
      </span>
      <input
        ref={inputRef}
        id={id}
        type="file"
        name="file"
        accept={accept}
        required
        aria-label={title}
        aria-describedby={`${helpId}${error ? ` ${errorId}` : ""}`}
        aria-invalid={Boolean(error)}
        onChange={onChange}
      />
      {error && (
        <small id={errorId} className="file-error" role="alert">
          {error}
        </small>
      )}
    </label>
  );
}
