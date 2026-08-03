import { useState } from "react";

import { StepIndicator } from "../../components/StepIndicator";
import { Step1UploadFiles } from "./Step1UploadFiles";
import { Step2DesignatePrimary } from "./Step2DesignatePrimary";
import { Step3Confirmation } from "./Step3Confirmation";

export default function NewAnalysisWizard() {
  const [currentStep, setCurrentStep] = useState(1);

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6">
      <StepIndicator currentStep={currentStep} />

      {currentStep === 1 ? <Step1UploadFiles onNext={() => setCurrentStep(2)} /> : null}
      {currentStep === 2 ? <Step2DesignatePrimary /> : null}
      {currentStep === 3 ? <Step3Confirmation /> : null}
    </div>
  );
}
