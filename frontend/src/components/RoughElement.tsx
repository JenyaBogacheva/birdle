import { useEffect, useRef } from 'react';
import { useRough } from '../hooks/useRough';

interface RoughElementProps {
  type: 'circle' | 'line' | 'rectangle';
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  x2?: number;
  y2?: number;
  options?: Record<string, unknown>;
  className?: string;
  animate?: boolean;
}

export default function RoughElement({
  type, x = 0, y = 0, width = 100, height = 100,
  x2 = 100, y2 = 100, options = {}, className = '', animate = true,
}: RoughElementProps) {
  const { svgRef, rc } = useRough();
  const drawnRef = useRef(false);
  const optionsRef = useRef(options);

  useEffect(() => {
    if (!rc || !svgRef.current || drawnRef.current) return;
    drawnRef.current = true;

    const drawOptions = {
      stroke: 'rgba(255,255,255,0.7)',
      strokeWidth: 1.5,
      roughness: 1.5,
      ...optionsRef.current,
    };

    let node: SVGGElement | undefined;
    switch (type) {
      case 'circle':
        node = rc.circle(x + width / 2, y + height / 2, width, drawOptions);
        break;
      case 'rectangle':
        node = rc.rectangle(x, y, width, height, drawOptions);
        break;
      case 'line':
        node = rc.line(x, y, x2, y2, drawOptions);
        break;
    }

    if (!node) return;

    if (animate) {
      const paths = node.querySelectorAll('path');
      paths.forEach((path) => {
        const length = path.getTotalLength();
        path.style.strokeDasharray = `${length}`;
        path.style.strokeDashoffset = `${length}`;
        path.style.animation = `drawIn 0.8s ease-out forwards`;
      });
    }

    svgRef.current.appendChild(node);
  }, [rc, svgRef, type, x, y, width, height, x2, y2, animate]);

  return (
    <svg
      ref={svgRef}
      className={`absolute inset-0 pointer-events-none ${className}`}
      width="100%"
      height="100%"
    />
  );
}
