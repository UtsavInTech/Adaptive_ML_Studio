/** Minimal React wrapper around uPlot: canvas drawing, data appended in place, one resize observer.
 *  Charts are recreated only when their options identity changes (theme, series set), never per update. */

import { useEffect, useRef } from "react";
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";

type Props = {
  options: uPlot.Options;
  data: uPlot.AlignedData;
  height: number;
  className?: string;
};

export default function UPlotChart({ options, data, height, className }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const plot = useRef<uPlot | null>(null);
  const latest = useRef(data);
  latest.current = data;

  useEffect(() => {
    const element = host.current;
    if (!element) return;
    const width = element.clientWidth || 600;
    const chart = new uPlot({ ...options, width, height }, latest.current, element);
    plot.current = chart;
    const observer = new ResizeObserver(([entry]) => {
      const next = Math.floor(entry.contentRect.width);
      if (next > 0) chart.setSize({ width: next, height });
    });
    observer.observe(element);
    return () => {
      observer.disconnect();
      chart.destroy();
      plot.current = null;
    };
  }, [options, height]);

  useEffect(() => {
    plot.current?.setData(data);
  }, [data]);

  return <div ref={host} className={`chart ${className ?? ""}`} />;
}
