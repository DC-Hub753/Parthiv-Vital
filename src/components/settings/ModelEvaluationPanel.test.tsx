import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { ModelEvaluationPanel } from './ModelEvaluationPanel.tsx';

const payload={model_version:'synthetic-logreg-0.2.0',algorithm:'StandardScaler + LogisticRegression',mode:'synthetic_demo',selected_candidate:null,candidates:{},training_data_version:null,clinical_training_verified:false,clinically_validated:false,demo_only:true,limitations:['No verified evaluation manifest is configured.']};
describe('ModelEvaluationPanel',()=>{
 beforeEach(()=>{vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>payload}));});
 afterEach(()=>vi.unstubAllGlobals());
 it('shows active model mode and limitations without inventing metrics',async()=>{
  render(<ModelEvaluationPanel/>);
  expect(await screen.findByText(/synthetic-logreg-0.2.0/)).toBeInTheDocument();
  expect(screen.getByText(/No verified evaluation manifest/)).toBeInTheDocument();
  expect(screen.queryByText(/100.0%/)).not.toBeInTheDocument();
 });
 it('shows a useful message when evaluation metadata is unavailable',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockRejectedValue(new Error('offline')));
  render(<ModelEvaluationPanel/>);
  expect(await screen.findByRole('alert')).toHaveTextContent(/metadata endpoint is unavailable/i);
 });
});
