import {useEffect,useState} from 'react';
import {Link} from 'react-router-dom';
import * as api from '../api/client';
import {continueHref,defectShare,defectTotal,heatmapForFilter} from '../dashboardStats';
import {coveragePercent} from '../projectSlug';
import type {DashboardStats} from '../types';
import {formatSpent} from './TimeChip';
import {MaskHeatmap} from './MaskHeatmap';

function formatCount(value:number){
  return new Intl.NumberFormat().format(Math.round(value||0));
}

function formatPixels(value:number){
  if(!value)return '—';
  if(value>=1_000_000)return `${(value/1_000_000).toFixed(2)} MP`;
  if(value>=1000)return `${Math.round(value/1000)}k px`;
  return `${Math.round(value)} px`;
}

export function DashboardPage(){
  const [report,setReport]=useState<DashboardStats|null>(null);
  const [error,setError]=useState<string|null>(null);
  const [heatFilter,setHeatFilter]=useState('all');
  useEffect(()=>{
    let stop=false;
    let timer=0;
    const load=async()=>{
      try{
        const next=await api.getStats();
        if(stop)return true;
        setReport(next);
        setError(null);
        return true;
      }catch(e){
        if(!stop)setError(e instanceof Error?e.message:String(e));
        return false;
      }
    };
    const tick=async()=>{if(await load())window.clearInterval(timer)};
    tick();
    timer=window.setInterval(tick,2000);
    return()=>{stop=true;window.clearInterval(timer)};
  },[]);

  const coverage=coveragePercent(report?.frames_annotated??0,report?.frames_extracted??0);
  const defectCounts=report?.defects.map(item=>item.count)??[];
  const mixTotal=defectTotal(defectCounts);
  const maxDefect=Math.max(1,...defectCounts,1);
  const heat=report?heatmapForFilter(report,heatFilter):null;
  const heatOptions=[{name:'all',label:'All defects'},...(report?.defects.map(item=>({name:item.name,label:item.name}))??[])];

  return <main className="dashboard">
      <section className="dash-hero">
        <h1>Annotation overview</h1>
        <Link className="primary dash-continue" to={continueHref(report?.continue)}>Continue Annotation →</Link>
      </section>

      {error&&!report&&<div className="empty-state dash-empty">
        <h2>Waiting for backend</h2>
        <p>{error}</p>
      </div>}

      {report&&<>
        <section className="kpi-grid">
          <article className="kpi-card">
            <span>Frames</span>
            <strong>{formatCount(report.frames_extracted)}</strong>
          </article>
          <article className="kpi-card">
            <span>Annotated</span>
            <strong>{formatCount(report.frames_annotated)}</strong>
          </article>
          <article className="kpi-card kpi-coverage">
            <div className="coverage-meter" style={{['--coverage' as string]:`${coverage}%`}}>
              <b>{coverage}%</b>
              <span>Complete</span>
            </div>
            <div className="coverage-copy">
              <span>Complete</span>
              <strong>{coverage}%</strong>
              <div className="coverage-bar" aria-hidden="true"><i style={{width:`${coverage}%`}}/></div>
            </div>
          </article>
        </section>

        <section className="dash-split dash-work">
          <article className="dash-panel defect-panel">
            <div className="section-title">
              <div>
                <h2>Defect distribution</h2>
                <p>Saved annotations by class.</p>
              </div>
            </div>
            <div className="defect-bars">
              {report.defects.length?report.defects.map(item=>{
                const share=defectShare(item.count,mixTotal);
                return <div className="defect-row" key={item.name}>
                  <div className="defect-name">
                    <i style={{background:item.color}}/>
                    <strong>{item.name}</strong>
                  </div>
                  <div className="defect-track">
                    <b style={{width:`${(item.count/maxDefect)*100}%`,background:item.color}}/>
                  </div>
                  <span className="defect-count">{formatCount(item.count)}</span>
                  <span className="defect-share">{share}%</span>
                </div>;
              }):<p className="dash-help">No defect annotations yet.</p>}
            </div>
          </article>
          <article className="dash-panel activity-panel">
            <div className="section-title">
              <div>
                <h2>Annotation activity</h2>
                <p>Media and time on this dataset.</p>
              </div>
            </div>
            <div className="activity-lines">
              <div><span>Videos</span><b>{formatCount(report.video_count)}</b></div>
              <div><span>Images</span><b>{formatCount(report.image_count)}</b></div>
              <div><span>Annotation time</span><b>{formatSpent(report.seconds_total)}</b></div>
              <div><span>Avg. frame</span><b>{report.avg_width&&report.avg_height?`${report.avg_width} × ${report.avg_height}`:'—'}</b></div>
            </div>
          </article>
        </section>

        <section className="dash-panel heatmap-panel">
          <div className="section-title">
            <div>
              <h2>Mask location heatmap</h2>
              <p>Where annotated pixels fall after every frame is scaled to the same pipe canvas.</p>
            </div>
          </div>
          <div className="heat-filters" role="tablist" aria-label="Heatmap defect filter">
            {heatOptions.map(option=>(
              <button
                key={option.name}
                type="button"
                role="tab"
                aria-selected={heatFilter===option.name}
                className={`heat-chip${heatFilter===option.name?' active':''}`}
                onClick={()=>setHeatFilter(option.name)}
              >{option.label}</button>
            ))}
          </div>
          <div className="heatmap-frame">
            {heat&&<MaskHeatmap values={heat.values}/>}
            <div className="heatmap-legend"><span>Idle</span><i/><span>Hot</span></div>
          </div>
        </section>

        <section className="dash-panel details-panel">
          <div className="section-title">
            <div>
              <h2>Dataset details</h2>
              <p>Mask size clusters from {formatCount(report.mask_count)} saved masks.</p>
            </div>
          </div>
          <div className="cluster-list">
            {report.mask_size_clusters.length?report.mask_size_clusters.map(cluster=>(
              <div className="cluster-row" key={cluster.label}>
                <strong>{cluster.label}</strong>
                <span>{formatCount(cluster.count)} · {Math.round(cluster.share*100)}%</span>
                <b>{formatPixels(cluster.mean_pixels)}</b>
              </div>
            )):<p className="dash-help">Save masks to see compact / typical / large clusters.</p>}
          </div>
        </section>
      </>}
    </main>;
}
