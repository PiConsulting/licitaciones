import { useState } from "react";

import { StepIndicator } from "../../components/StepIndicator";
import type { DuplicateDecision } from "../../types/analysis";
import type { UploadedFile } from "../../types/upload";
import { Step1UploadFiles } from "./Step1UploadFiles";
import { Step2DesignatePrimary } from "./Step2DesignatePrimary";
import { Step3Confirmation } from "./Step3Confirmation";
import { Step4StartAnalysis } from "./Step4StartAnalysis";

const STEP_TITLES = ["Subir archivos", "Designar principal", "Confirmación", "Iniciar análisis"];

export default function NewAnalysisWizard() {
  const [currentStep, setCurrentStep] = useState(1);
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [primaryIndex, setPrimaryIndex] = useState<number | null>(null);
  const [analysisId, setAnalysisId] = useState<string | null>(null);
  const [initialDecisions, setInitialDecisions] = useState<DuplicateDecision[]>([]);

  const handleStep1Next = (selectedFiles: UploadedFile[]) => {
    setFiles(selectedFiles);
    if (selectedFiles.length === 1) {
      setPrimaryIndex(0);
      setCurrentStep(3);
      return;
    }
    setCurrentStep(2);
  };

  const handleStep2Next = (index: number) => {
    setPrimaryIndex(index);
    setCurrentStep(3);
  };

  const handleStep3Next = (newAnalysisId: string, decisions: DuplicateDecision[]) => {
    setAnalysisId(newAnalysisId);
    setInitialDecisions(decisions);
    setCurrentStep(4);
  };

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6">
      <StepIndicator currentStep={currentStep} totalSteps={4} stepTitles={STEP_TITLES} />

      {currentStep === 1 ? <Step1UploadFiles onNext={handleStep1Next} /> : null}
      {currentStep === 2 ? (
        <Step2DesignatePrimary
          files={files}
          onBack={() => setCurrentStep(1)}
          onNext={handleStep2Next}
        />
      ) : null}
      {currentStep === 3 && primaryIndex !== null ? (
        <Step3Confirmation
          files={files}
          primaryIndex={primaryIndex}
          onBack={() => setCurrentStep(files.length > 1 ? 2 : 1)}
          onContinueToStart={handleStep3Next}
        />
      ) : null}
      {currentStep === 4 && analysisId ? (
        <Step4StartAnalysis
          analysisId={analysisId}
          initialDecisions={initialDecisions}
          onBack={() => setCurrentStep(3)}
        />
      ) : null}
    </div>
  );
}
